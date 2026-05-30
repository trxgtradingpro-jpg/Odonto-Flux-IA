from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import logging
import json
import os
import re
import sys
import unicodedata
from hashlib import sha1
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class WhatsAppNumberUnavailableError(RuntimeError):
    pass


def is_process_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


class WhatsAppAutomation:
    def __init__(self):
        self.driver = None
        self.message_history = []
        self.unopened_messages = []
        self.sent_messages_history = []
        self.bridge_state = {"phone_to_conversation": {}, "contact_to_phone": {}}
        self.chrome_profile_dir = os.path.join(os.getcwd(), 'chrome_profile')
        self.local_env = self.load_local_env()
        self.bridge_api_base_url = self.get_runtime_setting(
            "WHATSAPP_WEB_BRIDGE_API_BASE_URL",
            "http://localhost:8000/api/v1/internal/whatsapp-web",
        ).rstrip("/")
        self.bridge_token = self.get_runtime_setting("WHATSAPP_WEB_BRIDGE_TOKEN", "")
        self.bridge_poll_seconds = int(self.get_runtime_setting("WHATSAPP_WEB_BRIDGE_POLL_SECONDS", "4") or "4")
        self.load_bridge_state()
        # Baseline do chat aberto para detectar novas mensagens sem depender do badge de não lidas.
        self.processed_message_keys = set()
        self.active_chat_baselines = {}
        self.last_outbound_chat = None
        self.bridge_hold_until = {}
        self.shared_contact_capture_cache = {}
        self.setup_driver()
        
    def setup_driver(self):
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=WebRtcHideLocalIpsWithMdns')
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        options.add_argument('--start-maximized')
        options.add_argument('--no-first-run')
        options.add_argument('--no-default-browser-check')
        options.page_load_strategy = 'eager'
        # Mantem a sessão do WhatsApp Web entre execuções para evitar novo QR a cada teste.
        try:
            profile_dir = self.chrome_profile_dir
            os.makedirs(profile_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={profile_dir}")
            options.add_argument('--profile-directory=Default')
            # Pequenos ajustes para reduzir atrito com a detecção de automação do navegador.
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
        except Exception as e:
            logging.warning(f"Could not set profile dir: {e}")

        try:
            self.driver = webdriver.Chrome(options=options)
        except Exception as e:
            error_text = str(e or "")
            lock_path = Path(self.chrome_profile_dir) / "lockfile"
            if lock_path.exists() and ("session not created" in error_text.lower() or "devtoolsactiveport" in error_text.lower()):
                raise RuntimeError(
                    f"O perfil do Chrome usado pelo bot esta ocupado: {self.chrome_profile_dir}. "
                    "Feche a janela anterior do WhatsApp Web/Selenium que estiver usando esse perfil e rode novamente."
                ) from e
            raise
        self.driver.set_page_load_timeout(60)
        self.driver.set_script_timeout(30)
        logging.info(f"Chrome driver initialized successfully (profile: {os.path.abspath(self.chrome_profile_dir)})")

    def restart_driver_session(self):
        try:
            if self.driver is not None:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        time.sleep(1)
        self.setup_driver()

    def normalize_url_for_match(self, url):
        return str(url or "").strip().lower().rstrip("/")

    def cleanup_driver_tabs(self):
        try:
            handles = list(self.driver.window_handles)
        except Exception:
            return
        if not handles:
            return

        primary = handles[0]
        for handle in handles[1:]:
            try:
                self.driver.switch_to.window(handle)
                self.driver.close()
            except Exception:
                continue

        try:
            self.driver.switch_to.window(primary)
        except Exception:
            pass

    def open_url_with_retries(self, url, *, timeout=60, retries=3):
        last_error = None
        normalized_target = self.normalize_url_for_match(url)
        for attempt in range(1, retries + 1):
            try:
                self.cleanup_driver_tabs()
                self.driver.set_page_load_timeout(timeout)
                self.driver.get(url)
                return
            except TimeoutException as e:
                last_error = e
                logging.warning("Navigation timeout opening %s (attempt %s/%s)", url, attempt, retries)
                try:
                    self.driver.execute_script("window.stop();")
                except Exception:
                    pass

                try:
                    current_url = self.normalize_url_for_match(self.driver.current_url)
                except Exception:
                    current_url = ""
                if normalized_target and current_url and (
                    normalized_target in current_url or current_url in normalized_target
                ):
                    logging.info("Continuing after partial page load for %s (current URL: %s)", url, current_url)
                    return
            except Exception as e:
                last_error = e
                logging.warning("Navigation error opening %s (attempt %s/%s): %s", url, attempt, retries, e)

            if attempt < retries:
                try:
                    self.driver.get("about:blank")
                except Exception:
                    pass
                time.sleep(2)

        if last_error:
            raise last_error

    def find_env_file(self):
        current = Path(__file__).resolve()
        for parent in current.parents:
            candidate = parent / ".env"
            if candidate.exists():
                return candidate
        return None

    def load_local_env(self):
        values = {}
        env_file = self.find_env_file()
        if not env_file:
            return values
        try:
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
        except Exception as e:
            logging.warning(f"Could not load .env file: {e}")
        return values

    def get_runtime_setting(self, key, default=""):
        value = os.getenv(key)
        if value is None:
            value = self.local_env.get(key)
        return value if value not in [None, ""] else default

    def load_bridge_state(self):
        try:
            if os.path.exists("whatsapp_bridge_state.json"):
                with open("whatsapp_bridge_state.json", "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.bridge_state = {
                        "phone_to_conversation": data.get("phone_to_conversation", {}) if isinstance(data.get("phone_to_conversation"), dict) else {},
                        "contact_to_phone": data.get("contact_to_phone", {}) if isinstance(data.get("contact_to_phone"), dict) else {},
                    }
        except Exception as e:
            logging.error(f"Error loading bridge state: {e}")

    def save_bridge_state(self):
        try:
            with open("whatsapp_bridge_state.json", "w", encoding="utf-8-sig") as f:
                json.dump(self.bridge_state, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error saving bridge state: {e}")
        
    def save_data(self):
        """Save all data to JSON files"""
        try:
            # Save message history
            with open('message_history.json', 'w', encoding='utf-8-sig') as f:
                json.dump(self.message_history, f, indent=4, ensure_ascii=False)
                
            # Save unopened messages
            with open('unopened_messages.json', 'w', encoding='utf-8-sig') as f:
                json.dump(self.unopened_messages, f, indent=4, ensure_ascii=False)

            # Save sent messages history
            with open('sent_messages_history.json', 'w', encoding='utf-8-sig') as f:
                json.dump(self.sent_messages_history, f, indent=4, ensure_ascii=False)
                
            logging.info("Data saved successfully")
        except Exception as e:
            logging.error(f"Error saving data: {e}")
    
    def load_data(self, silent=False):
        """Load data from JSON files"""
        try:
            # O histórico é usado também como proteção contra duplicatas no monitor contínuo.
            if os.path.exists('message_history.json'):
                with open('message_history.json', 'r', encoding='utf-8-sig') as f:
                    self.message_history = json.load(f)
                if not silent:
                    logging.info("Message history loaded")
                self.processed_message_keys = {
                    self.build_message_key(item)
                    for item in self.message_history
                    if isinstance(item, dict)
                }
            
            # Load unopened messages
            if os.path.exists('unopened_messages.json'):
                with open('unopened_messages.json', 'r', encoding='utf-8-sig') as f:
                    self.unopened_messages = json.load(f)
                if not silent:
                    logging.info("Unopened messages loaded")

            # Load sent messages history
            if os.path.exists('sent_messages_history.json'):
                with open('sent_messages_history.json', 'r', encoding='utf-8-sig') as f:
                    self.sent_messages_history = json.load(f)
                if not silent:
                    logging.info("Sent messages history loaded")
                
        except Exception as e:
            logging.error(f"Error loading data: {e}")

    def build_message_key(self, message_data):
        # A chave usa contato + telefone + horário visível + texto para separar mensagens iguais em horários diferentes.
        contact = self.normalize_text(message_data.get('contact', ''))
        phone = self.normalize_text(message_data.get('phone_number', ''))
        text = self.normalize_text(
            message_data.get('message')
            or message_data.get('last_message')
            or ''
        )
        visible_time = self.normalize_text(message_data.get('visible_time', ''))
        return f"{contact}|{phone}|{visible_time}|{text}"

    def is_new_message(self, message_data):
        return self.build_message_key(message_data) not in self.processed_message_keys

    def register_message(self, message_data):
        key = self.build_message_key(message_data)
        if key in self.processed_message_keys:
            return False
        self.processed_message_keys.add(key)
        self.message_history.append(message_data)
        return True

    def append_sent_message_history(self, entry):
        self.load_data(silent=True)
        self.sent_messages_history.append(entry)
        self.save_data()

    def bridge_request(self, method, path, payload=None, query=None):
        if not self.bridge_token:
            raise RuntimeError("WHATSAPP_WEB_BRIDGE_TOKEN nao configurado.")

        base_url = f"{self.bridge_api_base_url}/{path.lstrip('/')}"
        if query:
            filtered_query = {key: value for key, value in query.items() if value not in [None, ""]}
            if filtered_query:
                base_url = f"{base_url}?{urlencode(filtered_query)}"

        body = None
        headers = {
            "Authorization": f"Bearer {self.bridge_token}",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(base_url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=90) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Bridge HTTP {e.code}: {detail or e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"Bridge connection error: {e}") from e

    def pull_bridge_outbox(self, limit=5):
        payload = self.bridge_request("GET", "/outbox/pull", query={"limit": limit, "worker_id": os.environ.get("COMPUTERNAME", "local-selenium")})
        items = payload.get("items", [])
        return items if isinstance(items, list) else []

    def remember_local_bridge_hold(self, outbox_id, review):
        if not outbox_id:
            return
        hold_until = None
        if isinstance(review, dict):
            raw_next_retry_at = str(review.get("next_retry_at") or "").strip()
            if raw_next_retry_at:
                try:
                    hold_until = datetime.fromisoformat(raw_next_retry_at.replace("Z", "+00:00"))
                except ValueError:
                    hold_until = None
            if hold_until is None:
                gate = review.get("gate") if isinstance(review.get("gate"), dict) else {}
                try:
                    wait_minutes = max(1, int(gate.get("wait_minutes") or 15))
                except (TypeError, ValueError):
                    wait_minutes = 15
                hold_until = datetime.now() + timedelta(minutes=wait_minutes)
        if hold_until is not None:
            self.bridge_hold_until[str(outbox_id)] = hold_until

    def is_local_bridge_hold_active(self, outbox_id):
        hold_until = self.bridge_hold_until.get(str(outbox_id))
        if not isinstance(hold_until, datetime):
            return False
        now_value = datetime.now(hold_until.tzinfo) if hold_until.tzinfo else datetime.now()
        if hold_until <= now_value:
            self.bridge_hold_until.pop(str(outbox_id), None)
            return False
        return True

    def acknowledge_bridge_outbox_success(self, outbox_id, send_result, item):
        payload = {
            "status": "sent",
            "provider_message_id": send_result.get("timestamp"),
            "external_chat_id": self.normalize_phone_number(item.get("phone_number", "")),
            "external_message_id": send_result.get("timestamp"),
            "sent_at": datetime.now().isoformat(),
        }
        return self.bridge_request("POST", f"/outbox/{outbox_id}/ack", payload=payload)

    def acknowledge_bridge_outbox_failure(self, outbox_id, error_message, retryable=True):
        payload = {
            "status": "failed" if retryable else "dead_letter",
            "retryable": retryable,
            "error": str(error_message or "Falha desconhecida ao enviar pelo WhatsApp Web."),
        }
        return self.bridge_request("POST", f"/outbox/{outbox_id}/ack", payload=payload)

    def sync_bridge_live_conversation(self, item, live_messages, contact_name=""):
        payload = {
            "conversation_id": item.get("conversation_id") or None,
            "phone_number": item.get("phone_number") or None,
            "contact_name": contact_name or "",
            "captured_at": datetime.now().isoformat(),
            "messages": live_messages,
        }
        return self.bridge_request("POST", "/conversation/sync", payload=payload)

    def review_bridge_live_send_gate(self, item, body, live_messages):
        payload = {
            "body": self.normalize_text(body or ""),
            "captured_at": datetime.now().isoformat(),
            "messages": live_messages,
        }
        return self.bridge_request("POST", f"/outbox/{item.get('id')}/live-review", payload=payload)

    def normalize_contact_key(self, contact_name):
        normalized = self.normalize_text(contact_name or "")
        return re.sub(r"\s+", " ", normalized).strip().lower()

    def get_bridge_mapping_by_phone(self, phone_number):
        if not phone_number:
            return None, None
        try:
            normalized_phone = self.normalize_phone_number(phone_number)
        except Exception:
            return None, None
        mapping = self.bridge_state.get("phone_to_conversation", {}).get(normalized_phone)
        if not isinstance(mapping, dict):
            return None, normalized_phone
        return mapping, normalized_phone

    def get_bridge_mapping_by_contact(self, contact_name):
        contact_key = self.normalize_contact_key(contact_name)
        if not contact_key:
            return None, None

        stored_phone = self.bridge_state.get("contact_to_phone", {}).get(contact_key)
        if stored_phone:
            mapping = self.bridge_state.get("phone_to_conversation", {}).get(stored_phone)
            if isinstance(mapping, dict):
                return mapping, stored_phone

        try:
            digits_only = self.normalize_phone_number(contact_name)
        except Exception:
            digits_only = None
        if digits_only:
            mapping = self.bridge_state.get("phone_to_conversation", {}).get(digits_only)
            if isinstance(mapping, dict):
                return mapping, digits_only
        return None, None

    def is_bridge_tracked_contact(self, contact_name):
        mapping, _ = self.get_bridge_mapping_by_contact(contact_name)
        return isinstance(mapping, dict)

    def remember_bridge_mapping(self, item, send_result=None):
        raw_phone = item.get("phone_number", "")
        conversation_id = item.get("conversation_id", "")
        if not raw_phone or not conversation_id:
            return
        try:
            normalized_phone = self.normalize_phone_number(raw_phone)
        except Exception:
            return
        chat_contact = ""
        if isinstance(send_result, dict):
            chat_contact = self.normalize_text(send_result.get("chat_contact") or "")
        self.bridge_state.setdefault("phone_to_conversation", {})[normalized_phone] = {
            "conversation_id": conversation_id,
            "prospect_account_id": item.get("prospect_account_id", ""),
            "step": item.get("step", ""),
            "contact_name": chat_contact,
            "updated_at": datetime.now().isoformat(),
        }
        if chat_contact:
            self.bridge_state.setdefault("contact_to_phone", {})[self.normalize_contact_key(chat_contact)] = normalized_phone
        self.save_bridge_state()

    def resolve_bridge_conversation(self, message_data):
        phone_number = (message_data.get("phone_number") or "").strip()
        contact_name = self.normalize_text(message_data.get("contact") or "")
        mapping, normalized_phone = self.get_bridge_mapping_by_phone(phone_number)
        if not isinstance(mapping, dict) and contact_name:
            mapping, normalized_phone = self.get_bridge_mapping_by_contact(contact_name)
        if not isinstance(mapping, dict):
            return None, normalized_phone or phone_number
        return mapping.get("conversation_id"), normalized_phone

    def forward_bridge_incoming_message(self, message_data):
        conversation_id, normalized_phone = self.resolve_bridge_conversation(message_data)
        if not conversation_id:
            logging.info(
                "Skipping inbound sync for unmapped chat: %s (%s)",
                message_data.get("contact") or "sem nome",
                normalized_phone or message_data.get("phone_number") or "sem telefone",
            )
            return {"status": "ignored_unmapped"}
        body_text = self.normalize_text(message_data.get("message") or message_data.get("last_message") or "")
        if not body_text and message_data.get("shared_contact_name"):
            body_text = self.build_shared_contact_message_text(
                message_data.get("shared_contact_name") or "",
                message_data.get("shared_contact_phone") or "",
            )
        payload = {
            "body": body_text,
            "conversation_id": conversation_id,
            "phone_number": normalized_phone or message_data.get("phone_number"),
            "contact_name": self.normalize_text(message_data.get("contact") or ""),
            "external_message_id": self.build_message_key(message_data),
            "external_chat_id": normalized_phone or "",
            "visible_time": message_data.get("visible_time") or "",
            "received_at": datetime.now().isoformat(),
        }
        if message_data.get("shared_contact_name"):
            payload["shared_contact_name"] = self.normalize_text(message_data.get("shared_contact_name") or "")
        if message_data.get("shared_contact_phone"):
            payload["shared_contact_phone"] = self.normalize_text(message_data.get("shared_contact_phone") or "")
        if not payload["body"]:
            return None
        return self.bridge_request("POST", "/inbound", payload=payload)

    def process_bridge_outbox_once(self, limit=5):
        items = self.pull_bridge_outbox(limit=limit)
        if not items:
            return []

        results = []
        for item in items:
            outbox_id = item.get("id")
            phone_number = item.get("phone_number")
            body = item.get("body")
            if not outbox_id or not phone_number or not body:
                if outbox_id:
                    self.acknowledge_bridge_outbox_failure(outbox_id, "Outbox incompleto recebido pelo bridge.", retryable=False)
                continue
            if self.is_local_bridge_hold_active(outbox_id):
                logging.info("Bridge local hold still active for outbox %s (%s); skipping reopen for now", outbox_id, phone_number)
                results.append({"outbox_id": outbox_id, "status": "held_local", "phone_number": phone_number})
                continue

            try:
                prepared = self.prepare_bridge_outbox_with_live_context(item, body)
                if not prepared:
                    logging.info("Bridge outbound held by live WhatsApp review: %s", phone_number)
                    results.append({"outbox_id": outbox_id, "status": "held", "phone_number": phone_number})
                    continue
                body = prepared.get("body") or body

                send_result = self.send_message_to_number(phone_number, body)
                if send_result:
                    self.remember_bridge_mapping(item, send_result)
                    self.last_outbound_chat = {
                        "contact": send_result.get("chat_contact") or phone_number,
                        "phone_number": self.normalize_phone_number(phone_number),
                        "conversation_id": item.get("conversation_id", ""),
                        "outbox_id": outbox_id,
                    }
                    self.acknowledge_bridge_outbox_success(outbox_id, send_result, item)
                    results.append({"outbox_id": outbox_id, "status": "sent", "phone_number": phone_number})
                else:
                    self.acknowledge_bridge_outbox_failure(outbox_id, f"Falha ao enviar mensagem para {phone_number}.", retryable=True)
                    results.append({"outbox_id": outbox_id, "status": "failed", "phone_number": phone_number})
            except WhatsAppNumberUnavailableError as e:
                reason = self.normalize_text(str(e) or f"O numero {phone_number} nao esta no WhatsApp.")
                logging.warning("Bridge outbound dead-letter for %s: %s", phone_number, reason)
                self.acknowledge_bridge_outbox_failure(outbox_id, reason, retryable=False)
                results.append({"outbox_id": outbox_id, "status": "dead_letter", "phone_number": phone_number})
            except Exception as e:
                logging.error(f"Bridge outbound unexpected error for {phone_number}: {e}")
                self.acknowledge_bridge_outbox_failure(outbox_id, f"Falha ao preparar ou enviar mensagem para {phone_number}: {e}", retryable=True)
                results.append({"outbox_id": outbox_id, "status": "failed", "phone_number": phone_number})
        return results

    def save_phone_capture_debug(self, contact_name, panel_preview, reason):
        try:
            debug_payload = {
                "timestamp": datetime.now().isoformat(),
                "contact": contact_name,
                "reason": reason,
                "panel_preview": panel_preview,
            }
            with open('phone_capture_debug.json', 'w', encoding='utf-8-sig') as f:
                json.dump(debug_payload, f, indent=4, ensure_ascii=False)
            logging.info("Saved phone capture debug to phone_capture_debug.json")
        except Exception as e:
            logging.error(f"Error saving phone capture debug: {e}")

    def clear_phone_capture_debug(self):
        try:
            if os.path.exists('phone_capture_debug.json'):
                os.remove('phone_capture_debug.json')
                logging.info("Cleared stale phone_capture_debug.json after successful phone capture")
        except Exception as e:
            logging.error(f"Error clearing phone capture debug: {e}")

    def save_contact_panel_artifacts(self, contact_name):
        try:
            safe_contact = re.sub(r"[^a-zA-Z0-9_-]+", "_", contact_name or "unknown").strip("_") or "unknown"
            html = self.driver.execute_script(
                """
                const headers = Array.from(document.querySelectorAll('header'));
                const target = headers.length ? headers[headers.length - 1] : document.body;
                return target ? target.outerHTML : document.body.outerHTML;
                """
            )
            with open(f'phone_capture_debug_{safe_contact}.html', 'w', encoding='utf-8-sig') as f:
                f.write(html)
            self.driver.save_screenshot(f'phone_capture_debug_{safe_contact}.png')
            logging.info(f"Saved contact panel artifacts for {contact_name}")
        except Exception as e:
            logging.error(f"Error saving contact panel artifacts: {e}")

    def save_contact_panel_body_artifacts(self, contact_name, panel):
        try:
            safe_contact = re.sub(r"[^a-zA-Z0-9_-]+", "_", contact_name or "unknown").strip("_") or "unknown"
            panel_html = self.driver.execute_script("return arguments[0].outerHTML;", panel)
            with open(f'phone_capture_panel_{safe_contact}.html', 'w', encoding='utf-8-sig') as f:
                f.write(panel_html)
            logging.info(f"Saved contact panel body HTML for {contact_name}")
        except Exception as e:
            logging.error(f"Error saving contact panel body HTML: {e}")

    def save_message_capture_artifacts(self, contact_name, reason):
        try:
            safe_contact = re.sub(r"[^a-zA-Z0-9_-]+", "_", contact_name or "unknown").strip("_") or "unknown"
            payload = {
                "timestamp": datetime.now().isoformat(),
                "contact": contact_name,
                "reason": reason,
            }
            with open(f'message_capture_debug_{safe_contact}.json', 'w', encoding='utf-8-sig') as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)

            containers_html = self.driver.execute_script(
                """
                const nodes = Array.from(document.querySelectorAll("div[data-testid='msg-container']")).slice(-8);
                return nodes.map((node, index) => `<!-- container:${index} -->\\n${node.outerHTML}`).join("\\n\\n");
                """
            )
            if containers_html:
                with open(f'message_capture_debug_{safe_contact}.html', 'w', encoding='utf-8-sig') as f:
                    f.write(containers_html)

            self.driver.save_screenshot(f'message_capture_debug_{safe_contact}.png')
            logging.info(f"Saved message capture artifacts for {contact_name}")
        except Exception as e:
            logging.error(f"Error saving message capture artifacts: {e}")

    def get_active_chat_header(self):
        # O WhatsApp renderiza mais de um <header>; aqui filtramos para achar o cabeçalho da conversa, não o painel lateral.
        try:
            headers = self.driver.find_elements(By.XPATH, "//header")
            if not headers:
                return None

            for header in reversed(headers):
                try:
                    text = self.normalize_text(header.text or "")
                    normalized_text = text.lower()
                    if not text:
                        continue
                    if normalized_text in {"dados do contato", "informações do contato", "contact info", "group info", "dados do grupo"}:
                        continue
                    if "dados do contato" in normalized_text or "contact info" in normalized_text:
                        continue
                    if header.find_elements(By.XPATH, ".//*[@data-testid='conversation-info-header-chat-title']"):
                        return header
                    if header.find_elements(By.XPATH, ".//span[@title] | .//span[@dir='auto']"):
                        return header
                except Exception:
                    continue

            for header in reversed(headers):
                try:
                    text = self.normalize_text(header.text or "")
                    normalized_text = text.lower()
                    if text and "dados do contato" not in normalized_text and "contact info" not in normalized_text:
                        return header
                except Exception:
                    continue

            return headers[-1]
        except Exception:
            return None

    def close_contact_info_panel_if_present(self):
        try:
            close_selectors = [
                "//button[@aria-label='Fechar']",
                "//button[@aria-label='Close']",
                "//div[@role='button' and @aria-label='Fechar']",
                "//div[@role='button' and @aria-label='Close']",
                "//*[@data-testid='x']/ancestor::button[1]",
                "//*[@data-icon='x']/ancestor::button[1]",
            ]

            for selector in close_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for button in buttons:
                        if not button.is_displayed():
                            continue
                        try:
                            label = self.normalize_text(
                                (button.get_attribute("aria-label") or button.text or "").strip()
                            ).lower()
                        except Exception:
                            label = ""

                        if label and label not in {"fechar", "close"} and "dados do contato" not in label:
                            continue

                        try:
                            button.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", button)
                        time.sleep(0.4)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def normalize_text(self, text):
        """Repair common mojibake cases and normalize whitespace."""
        if not text:
            return text

        normalized = text.replace("\u00a0", " ").strip()
        broken_markers = ("Ã", "Â", "â€™", "â€œ", "â€", "ðŸ")
        if any(marker in normalized for marker in broken_markers):
            try:
                repaired = normalized.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore").strip()
                if repaired:
                    normalized = repaired
            except Exception:
                pass

        return normalized

    def normalize_contact_match_key(self, text):
        normalized = self.normalize_text(text or "")
        normalized = unicodedata.normalize("NFKD", normalized)
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()
        return normalized

    def looks_like_phone_label(self, text):
        normalized = self.normalize_text(text or "").strip()
        if not normalized:
            return False
        digits_only = re.sub(r"\D+", "", normalized)
        return len(digits_only) >= 10 and len(digits_only) >= max(10, len(normalized) - 4)

    def detect_unavailable_whatsapp_alert(self):
        phrases = (
            "nao esta no whatsapp",
            "numero nao esta no whatsapp",
            "isn't on whatsapp",
            "is not on whatsapp",
            "phone number shared via url is invalid",
            "numero de telefone compartilhado por url e invalido",
            "nao tem uma conta no whatsapp",
        )
        selectors = [
            "//div[@role='dialog']",
            "//div[contains(@data-animate-modal-popup, 'true')]",
            "//div[contains(@class,'x1n2onr6')]",
        ]

        for selector in selectors:
            try:
                for elem in self.driver.find_elements(By.XPATH, selector):
                    text = self.normalize_text(elem.text or "")
                    normalized_text = self.normalize_contact_match_key(text)
                    if text and any(phrase in normalized_text for phrase in phrases):
                        return text
            except Exception:
                continue

        try:
            body_text = self.normalize_text(self.driver.find_element(By.TAG_NAME, "body").text or "")
            normalized_body = self.normalize_contact_match_key(body_text)
            for phrase in phrases:
                if phrase in normalized_body:
                    return body_text
        except Exception:
            pass
        return None

    def dismiss_unavailable_whatsapp_alert(self):
        selectors = [
            "//div[@role='dialog']//button[normalize-space()='OK']",
            "//div[@role='dialog']//*[@role='button'][normalize-space()='OK']",
            "//div[@role='dialog']//button[@aria-label='OK']",
            "//div[@role='dialog']//*[@role='button'][@aria-label='OK']",
        ]
        for selector in selectors:
            try:
                button = self.driver.find_element(By.XPATH, selector)
                try:
                    button.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", button)
                time.sleep(0.5)
                return True
            except Exception:
                continue
        return False

    def wait_for_chat_input_or_unavailable_alert(self, timeout=40):
        composer_xpath = "//footer//div[@contenteditable='true']"

        def resolve_state(driver):
            alert_text = self.detect_unavailable_whatsapp_alert()
            if alert_text:
                return {"state": "unavailable", "message": alert_text}

            try:
                send_box = driver.find_element(By.XPATH, composer_xpath)
                if send_box.is_displayed() and send_box.is_enabled():
                    return {"state": "composer", "element": send_box}
            except Exception:
                pass
            return False

        try:
            return WebDriverWait(self.driver, timeout).until(resolve_state)
        except TimeoutException as exc:
            alert_text = self.detect_unavailable_whatsapp_alert()
            if alert_text:
                return {"state": "unavailable", "message": alert_text}
            raise exc

    def phone_numbers_match(self, expected_phone, actual_phone):
        try:
            expected_digits = self.normalize_phone_number(expected_phone)
            actual_digits = self.normalize_phone_number(actual_phone)
        except Exception:
            return False

        if expected_digits == actual_digits:
            return True

        # Aceita pequenas diferencas de formato, como titulo sem DDI.
        return expected_digits.endswith(actual_digits) or actual_digits.endswith(expected_digits)

    def get_open_chat_phone_candidate(self):
        header_name = self.extract_open_chat_contact_name() or ""
        candidate_sources = [
            self.extract_contact_number_from_open_chat(header_name),
            header_name,
        ]
        for candidate in candidate_sources:
            try:
                normalized_candidate = self.normalize_phone_number(candidate)
                if normalized_candidate:
                    return normalized_candidate
            except Exception:
                continue
        return ""

    def wait_for_target_chat_match(self, phone_number, composer_element=None, timeout=12):
        deadline = time.time() + max(1, timeout)
        last_seen = ""
        while time.time() < deadline:
            if composer_element is not None:
                try:
                    if not composer_element.is_displayed():
                        composer_element = None
                except Exception:
                    composer_element = None

            if composer_element is None:
                try:
                    composer_element = self.driver.find_element(By.XPATH, "//footer//div[@contenteditable='true']")
                except Exception:
                    time.sleep(0.4)
                    continue

            open_chat_phone = self.get_open_chat_phone_candidate()
            if self.phone_numbers_match(phone_number, open_chat_phone):
                return composer_element

            last_seen = open_chat_phone or (self.extract_open_chat_contact_name() or "")
            time.sleep(0.6)

        raise TimeoutException(
            f"O chat aberto nao corresponde ao numero {phone_number}. "
            f"Conversa visivel: {last_seen or 'desconhecida'}."
        )

    def ensure_chat_available_for_phone(self, phone_number, timeout=40):
        deadline = time.time() + max(1, timeout)
        last_error = None

        while time.time() < deadline:
            remaining = max(1, int(deadline - time.time()))
            state = self.wait_for_chat_input_or_unavailable_alert(timeout=min(10, remaining))
            if isinstance(state, dict) and state.get("state") == "unavailable":
                alert_text = self.normalize_text(state.get("message") or "")
                self.dismiss_unavailable_whatsapp_alert()
                raise WhatsAppNumberUnavailableError(
                    alert_text or f"O numero {phone_number} nao esta no WhatsApp."
                )
            if isinstance(state, dict) and state.get("state") == "composer":
                try:
                    return self.wait_for_target_chat_match(
                        phone_number,
                        composer_element=state.get("element"),
                        timeout=min(8, max(2, remaining)),
                    )
                except TimeoutException as exc:
                    last_error = exc
                    logging.warning("Composer apareceu no chat errado para %s. Tentando reabrir...", phone_number)
                    try:
                        normalized_phone = self.normalize_phone_number(phone_number)
                        self.open_url_with_retries(
                            f"https://web.whatsapp.com/send?phone={normalized_phone}",
                            timeout=45,
                            retries=1,
                        )
                    except Exception as reopen_exc:
                        last_error = reopen_exc
                    time.sleep(0.8)
                    continue

        if last_error:
            raise last_error
        raise TimeoutException(f"Nao foi possivel abrir o composer do WhatsApp para {phone_number}.")

    def extract_contact_name(self, conversation_element):
        """Extract the real chat title instead of badge counts or preview text."""
        title_selectors = [
            ".//span[@title and @dir='auto']",
            ".//div[@role='gridcell']//span[@title]",
            ".//span[contains(@class, 'x1iyjqo2') and @title]",
            ".//*[@title]",
        ]

        for selector in title_selectors:
            try:
                elements = conversation_element.find_elements(By.XPATH, selector)
                for elem in elements:
                    title = (elem.get_attribute("title") or elem.text or "").strip()
                    title = self.normalize_text(title)
                    if title and not title.isdigit():
                        return title
            except Exception:
                continue

        try:
            cell_text = conversation_element.text.strip()
            lines = [line.strip() for line in cell_text.splitlines() if line.strip()]
            for line in lines:
                line = self.normalize_text(line)
                if not line.isdigit():
                    return line
        except Exception:
            pass

        return "Unknown"

    def get_unread_count(self, conversation_element):
        try:
            unread_elem = conversation_element.find_element(
                By.XPATH,
                self.unread_badge_xpath(),
            )
            count_text = unread_elem.text.strip()
            return int(count_text) if count_text.isdigit() else 1
        except Exception:
            return 1

    def unread_badge_xpath(self):
        return (
            ".//span[@data-testid='icon-unread-count']"
            " | .//span[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÀÃÂÉÊÍÓÔÕÚÇ', 'abcdefghijklmnopqrstuvwxyzáàãâéêíóôõúç'), 'unread')]"
            " | .//span[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÀÃÂÉÊÍÓÔÕÚÇ', 'abcdefghijklmnopqrstuvwxyzáàãâéêíóôõúç'), 'não lida')]"
            " | .//span[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÀÃÂÉÊÍÓÔÕÚÇ', 'abcdefghijklmnopqrstuvwxyzáàãâéêíóôõúç'), 'nao lida')]"
            " | .//span[@aria-label and normalize-space(text()) != '' and translate(normalize-space(text()), '0123456789', '') = '']"
        )

    def unread_chat_xpath(self):
        return f"//div[@data-testid='cell-frame-container'][{self.unread_badge_xpath()}]"

    def count_visible_unread_candidates(self):
        try:
            return len(self.driver.find_elements(By.XPATH, self.unread_chat_xpath()))
        except Exception:
            return 0

    def find_all_unopened_conversations(self, verbose=True):
        """Return all valid unread conversations currently visible."""
        try:
            wait = WebDriverWait(self.driver, 30)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

            unread_chats = self.driver.find_elements(
                By.XPATH,
                self.unread_chat_xpath(),
            )
            if verbose:
                logging.info(f"Found {len(unread_chats)} unread conversations")

            unopened = []
            for index, conv in enumerate(unread_chats):
                try:
                    title = self.extract_contact_name(conv)
                    if not self.is_valid_unread_conversation(title):
                        if verbose:
                            logging.info(f"Skipping unread item: {title}")
                        continue

                    unopened.append({
                        # Guardamos o índice para ter um fallback caso o elemento fique stale durante o clique.
                        'index': index,
                        'contact': title,
                        'unread_count': self.get_unread_count(conv)
                    })
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logging.warning(f"Error checking unread conversation: {e}")
                    continue

            return unopened
        except Exception as e:
            logging.error(f"Error finding unread conversations: {e}")
            return []

    def is_valid_unread_conversation(self, title):
        invalid_titles = {"arquivadas", "archived"}
        normalized = re.sub(r"\s+", " ", (title or "")).strip().lower()
        return bool(normalized and normalized not in invalid_titles)

    def find_first_unopened_conversation(self):
        """Return only the first valid unread conversation."""
        try:
            wait = WebDriverWait(self.driver, 30)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

            unread_chats = self.driver.find_elements(
                By.XPATH,
                self.unread_chat_xpath(),
            )
            logging.info(f"Found {len(unread_chats)} unread conversations")

            for index, conv in enumerate(unread_chats):
                try:
                    title = self.extract_contact_name(conv)
                    if not self.is_valid_unread_conversation(title):
                        logging.info(f"Skipping unread item: {title}")
                        continue

                    unread_count = self.get_unread_count(conv)
                    logging.info(f"Selected unopened conversation: {title} ({unread_count} unread)")
                    return {
                        'index': index,
                        'contact': title,
                        'unread_count': unread_count
                    }
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logging.warning(f"Error checking conversation: {e}")
                    continue

            return None
        except Exception as e:
            logging.error(f"Error finding unread conversation: {e}")
            return None

    def find_last_conversation(self):
        """Return the last visible conversation from the sidebar."""
        try:
            wait = WebDriverWait(self.driver, 30)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

            conversations = self.driver.find_elements(
                By.XPATH,
                "//div[@data-testid='cell-frame-container']"
            )
            logging.info(f"Found {len(conversations)} visible conversations")

            for index in range(len(conversations) - 1, -1, -1):
                try:
                    title = self.extract_contact_name(conversations[index])
                    if not self.is_valid_unread_conversation(title):
                        logging.info(f"Skipping conversation item: {title}")
                        continue

                    logging.info(f"Selected last conversation: {title}")
                    return {
                        'index': index,
                        'contact': title,
                        'unread_count': 0
                    }
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logging.warning(f"Error checking visible conversation: {e}")
                    continue

            return None
        except Exception as e:
            logging.error(f"Error finding last conversation: {e}")
            return None

    def wait_for_chat_to_open(self, contact_name):
        """Wait until the selected chat header matches the expected contact."""
        normalized_contact = self.normalize_contact_match_key(contact_name)
        contact_tokens = [token for token in normalized_contact.split(" ") if token]

        def chat_opened(driver):
            try:
                header_candidates = driver.find_elements(
                    By.XPATH,
                    "//header//span[@title] | //header//*[@title] | //header//span[@dir='auto']"
                )
                for elem in header_candidates:
                    text = ((elem.get_attribute("title") or elem.text) or "").strip()
                    normalized_text = self.normalize_contact_match_key(text)
                    if not normalized_text:
                        continue
                    if normalized_contact and (
                        normalized_contact in normalized_text or normalized_text in normalized_contact
                    ):
                        return True
                    if any(token in normalized_text for token in contact_tokens if len(token) >= 4):
                        return True
            except Exception:
                return False
            return False

        WebDriverWait(self.driver, 15).until(chat_opened)

    def open_unread_conversation(self, conversation_info):
        """Open the unread conversation by title, with index fallback and retries."""
        wait = WebDriverWait(self.driver, 20)
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))
        normalized_contact = self.normalize_contact_match_key(conversation_info['contact'])

        for attempt in range(3):
            try:
                # Rebusca os elementos a cada tentativa porque a sidebar muda bastante após novas mensagens.
                unread_chats = self.driver.find_elements(
                    By.XPATH,
                    self.unread_chat_xpath(),
                )

                target = None
                for elem in unread_chats:
                    try:
                        candidate = self.extract_contact_name(elem)
                        normalized_candidate = self.normalize_contact_match_key(candidate)
                        if normalized_candidate == normalized_contact:
                            target = elem
                            break
                    except StaleElementReferenceException:
                        continue

                if target is None and conversation_info['index'] < len(unread_chats):
                    target = unread_chats[conversation_info['index']]

                if target is None:
                    logging.warning("Unread target not found for contact: %s", conversation_info['contact'])
                    continue

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                time.sleep(0.5)
                logging.info("Opening unread chat: %s (attempt %s)", conversation_info['contact'], attempt + 1)

                try:
                    target.click()
                except Exception:
                    clickable = None
                    click_selectors = [
                        ".//div[@role='listitem']",
                        ".//div[@role='button']",
                        ".//*[@tabindex='0']",
                    ]
                    for selector in click_selectors:
                        try:
                            clickable = target.find_element(By.XPATH, selector)
                            break
                        except Exception:
                            continue
                    self.driver.execute_script("arguments[0].click();", clickable or target)

                self.wait_for_chat_to_open(conversation_info['contact'])
                return True
            except Exception as e:
                logging.warning(f"Attempt {attempt + 1} to open chat failed: {e}")
                time.sleep(1)

        return False

    def open_conversation_from_sidebar(self, conversation_info):
        """Open any visible conversation from the sidebar by title, with index fallback."""
        wait = WebDriverWait(self.driver, 20)
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))
        normalized_contact = re.sub(r"\s+", " ", conversation_info['contact']).strip().lower()

        for attempt in range(3):
            try:
                conversations = self.driver.find_elements(
                    By.XPATH,
                    "//div[@data-testid='cell-frame-container']"
                )

                target = None
                for elem in conversations:
                    try:
                        candidate = self.extract_contact_name(elem)
                        normalized_candidate = re.sub(r"\s+", " ", candidate).strip().lower()
                        if normalized_candidate == normalized_contact:
                            target = elem
                            break
                    except StaleElementReferenceException:
                        continue

                if target is None and conversation_info['index'] < len(conversations):
                    target = conversations[conversation_info['index']]

                if target is None:
                    continue

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                time.sleep(0.5)

                try:
                    target.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", target)

                self.wait_for_chat_to_open(conversation_info['contact'])
                return True
            except Exception as e:
                logging.warning(f"Attempt {attempt + 1} to open visible chat failed: {e}")
                time.sleep(1)

        return False

    def clean_message_lines(self, raw_lines):
        cleaned_lines = []
        ignored_actions = {
            "conversar",
            "mostrar empresa",
            "message",
            "mensagem",
            "forwarded",
            "encaminhada",
            "encaminhado",
        }
        for raw_line in raw_lines:
            line = self.normalize_text(str(raw_line or "").strip())
            if not line:
                continue
            lowered = line.lower()
            if re.fullmatch(r"\d{1,2}:\d{2}", line):
                continue
            if lowered in ignored_actions:
                continue
            cleaned_lines.append(line)
        return cleaned_lines

    def extract_shared_contact_from_container(self, container):
        try:
            raw_text = self.normalize_text(
                self.driver.execute_script("return arguments[0].innerText || arguments[0].textContent || '';", container)
            )
        except Exception:
            raw_text = ""

        if not raw_text:
            return None

        lowered = raw_text.lower()
        card_markers = ("conversar", "mostrar empresa")
        if not any(marker in lowered for marker in card_markers):
            return None

        cleaned_lines = self.clean_message_lines(raw_text.splitlines())
        if not cleaned_lines:
            return None

        shared_contact_name = cleaned_lines[0].strip()
        shared_contact_phone = ""
        for line in cleaned_lines:
            candidate = self.normalize_text(line)
            if re.search(r"(?:\+\d{1,3}\s*)?(?:\(?\d{2,3}\)?\s*)?(?:9?\d{4}[-\s]?\d{4}|\d{3,4}[-\s]?\d{4,5})", candidate or ""):
                shared_contact_phone = candidate
                break

        return {
            "shared_contact_name": shared_contact_name,
            "shared_contact_phone": shared_contact_phone,
        }

    def build_shared_contact_message_text(self, shared_contact_name, shared_contact_phone=""):
        normalized_name = self.normalize_text(shared_contact_name or "").strip()
        normalized_phone = self.normalize_text(shared_contact_phone or "").strip()
        if normalized_name and normalized_phone:
            return f"Contato compartilhado: {normalized_name} - {normalized_phone}"
        if normalized_name:
            return f"Contato compartilhado: {normalized_name}"
        if normalized_phone:
            return f"Contato compartilhado: {normalized_phone}"
        return ""

    def find_shared_contact_message_container(self, shared_contact_name, visible_time=""):
        target_name = self.normalize_contact_match_key(shared_contact_name)
        target_time = self.normalize_text(visible_time or "")
        if not target_name:
            return None

        message_containers = self.driver.find_elements(By.XPATH, "//div[@data-testid='msg-container']")
        for container in reversed(message_containers):
            try:
                shared_contact = self.extract_shared_contact_from_container(container) or {}
                candidate_name = self.normalize_contact_match_key(shared_contact.get("shared_contact_name") or "")
                if not candidate_name:
                    continue
                if target_name not in candidate_name and candidate_name not in target_name:
                    continue
                if target_time:
                    candidate_time = self.extract_visible_time_from_container(container)
                    if candidate_time and candidate_time != target_time:
                        continue
                return container
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        return None

    def open_sidebar_conversation_by_contact_name(self, contact_name):
        wait = WebDriverWait(self.driver, 20)
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))
        normalized_contact = self.normalize_contact_match_key(contact_name)
        if not normalized_contact:
            return False

        for attempt in range(3):
            try:
                conversations = self.driver.find_elements(By.XPATH, "//div[@data-testid='cell-frame-container']")
                target = None
                for elem in conversations:
                    try:
                        candidate = self.extract_contact_name(elem)
                        normalized_candidate = self.normalize_contact_match_key(candidate)
                        if not normalized_candidate:
                            continue
                        if (
                            normalized_candidate == normalized_contact
                            or normalized_contact in normalized_candidate
                            or normalized_candidate in normalized_contact
                        ):
                            target = elem
                            break
                    except StaleElementReferenceException:
                        continue

                if target is None:
                    continue

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                time.sleep(0.4)
                try:
                    target.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", target)

                self.wait_for_chat_to_open(contact_name)
                return True
            except Exception as e:
                logging.warning("Attempt %s to reopen chat %s failed: %s", attempt + 1, contact_name, e)
                time.sleep(0.8)

        return False

    def click_shared_contact_converse_button(self, container):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", container)
            time.sleep(0.3)
        except Exception:
            pass

        try:
            button = self.driver.execute_script(
                """
                const root = arguments[0];
                const wanted = ['conversar', 'message'];
                const nodes = Array.from(root.querySelectorAll('[role="button"], button, a, span, div'));
                for (const node of nodes) {
                    const text = (node.innerText || node.textContent || '').trim().toLowerCase();
                    if (wanted.includes(text)) {
                        return node.closest('[role="button"], button, a') || node;
                    }
                }
                return null;
                """,
                container,
            )
            if button is not None:
                try:
                    button.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", button)
                return True
        except Exception:
            pass

        fallback_selectors = [
            ".//*[@role='button'][contains(normalize-space(.), 'Conversar') or contains(normalize-space(.), 'Message')]",
            ".//button[contains(normalize-space(.), 'Conversar') or contains(normalize-space(.), 'Message')]",
            ".//*[contains(normalize-space(.), 'Conversar') or contains(normalize-space(.), 'Message')]/ancestor::*[@role='button'][1]",
        ]
        for selector in fallback_selectors:
            try:
                button = container.find_element(By.XPATH, selector)
                try:
                    button.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", button)
                return True
            except Exception:
                continue
        return False

    def wait_for_chat_change(self, previous_contact_name, timeout=10):
        previous_key = self.normalize_contact_match_key(previous_contact_name)

        def chat_changed(driver):
            current_name = self.extract_open_chat_contact_name() or ""
            current_key = self.normalize_contact_match_key(current_name)
            if current_key and current_key != previous_key:
                return current_name
            return False

        try:
            return WebDriverWait(self.driver, timeout).until(chat_changed)
        except Exception:
            return ""

    def capture_shared_contact_details_from_open_chat(self, source_contact_name, shared_contact_name, visible_time=""):
        source_key = self.normalize_contact_match_key(source_contact_name)
        target_key = self.normalize_contact_match_key(shared_contact_name)
        if not source_key or not target_key:
            return {}

        container = self.find_shared_contact_message_container(shared_contact_name, visible_time=visible_time)
        if container is None:
            logging.info(
                "Could not find shared contact card for %s inside %s",
                shared_contact_name,
                source_contact_name,
            )
            return {}

        try:
            if not self.click_shared_contact_converse_button(container):
                logging.info(
                    "Shared contact card for %s did not expose a clickable 'Conversar' button",
                    shared_contact_name,
                )
                return {}

            try:
                self.wait_for_chat_to_open(shared_contact_name)
                opened_chat_name = self.extract_open_chat_contact_name() or shared_contact_name
            except Exception:
                opened_chat_name = self.wait_for_chat_change(source_contact_name, timeout=10) or ""
                if not opened_chat_name:
                    logging.info(
                        "Shared contact card click did not switch chats for %s",
                        shared_contact_name,
                    )
                    return {}

            captured_phone = self.extract_contact_number_from_open_chat(opened_chat_name or shared_contact_name) or ""
            self.close_contact_info_panel_if_present()
            resolved_shared_name = opened_chat_name or shared_contact_name
            if self.looks_like_phone_label(resolved_shared_name):
                resolved_shared_name = shared_contact_name
            if captured_phone:
                logging.info(
                    "Captured shared contact phone from %s via %s: %s",
                    source_contact_name,
                    resolved_shared_name,
                    captured_phone,
                )
            else:
                logging.info(
                    "Opened shared contact chat for %s, but no phone number was visible",
                    resolved_shared_name,
                )
            return {
                "shared_contact_name": resolved_shared_name,
                "shared_contact_phone": captured_phone,
            }
        except Exception as e:
            logging.info(
                "Failed to capture shared contact phone for %s from %s: %s",
                shared_contact_name,
                source_contact_name,
                e,
            )
            return {}
        finally:
            try:
                current_chat = self.extract_open_chat_contact_name() or ""
                if self.normalize_contact_match_key(current_chat) != source_key:
                    reopened = self.open_sidebar_conversation_by_contact_name(source_contact_name)
                    if reopened:
                        time.sleep(0.5)
                    else:
                        logging.warning(
                            "Could not reopen source chat %s after shared contact capture",
                            source_contact_name,
                        )
            except Exception as reopen_error:
                logging.warning(
                    "Error while returning to source chat %s after shared contact capture: %s",
                    source_contact_name,
                    reopen_error,
                )

    def enrich_shared_contact_details(self, contact_name, collected_messages):
        if not collected_messages:
            return collected_messages

        source_contact_key = self.normalize_contact_match_key(contact_name)
        captured_by_key = {}
        for message_data in collected_messages:
            shared_contact_name = self.normalize_text(message_data.get("shared_contact_name") or "")
            shared_contact_phone = self.normalize_text(message_data.get("shared_contact_phone") or "")
            if not shared_contact_name or shared_contact_phone:
                continue

            visible_time = self.normalize_text(message_data.get("visible_time") or "")
            cache_key = f"{source_contact_key}|{self.normalize_contact_match_key(shared_contact_name)}|{visible_time}"
            if cache_key not in captured_by_key:
                cached_result = self.shared_contact_capture_cache.get(cache_key)
                if cached_result is None:
                    cached_result = self.capture_shared_contact_details_from_open_chat(
                        contact_name,
                        shared_contact_name,
                        visible_time=visible_time,
                    ) or {}
                    self.shared_contact_capture_cache[cache_key] = cached_result
                captured_by_key[cache_key] = cached_result

            captured = captured_by_key.get(cache_key) or {}
            captured_name = self.normalize_text(captured.get("shared_contact_name") or "")
            captured_phone = self.normalize_text(captured.get("shared_contact_phone") or "")
            if captured_name:
                message_data["shared_contact_name"] = captured_name
            if captured_phone:
                message_data["shared_contact_phone"] = captured_phone

        return collected_messages

    def extract_message_text_from_container(self, container):
        # O layout do WhatsApp muda conforme tipo de mensagem; por isso tentamos vários seletores antes do fallback bruto.
        selectors = [
            ".//div[contains(@class,'copyable-text')]//span[@dir='ltr' or @dir='auto']",
            ".//span[contains(@class,'selectable-text')]",
            ".//div[contains(@class,'copyable-text')]//span",
            ".//*[@data-testid='msg-text']//span",
            ".//span[@dir='ltr' or @dir='auto']",
        ]

        text_parts = []
        seen = set()

        for selector in selectors:
            try:
                elements = container.find_elements(By.XPATH, selector)
                for elem in elements:
                    text = self.normalize_text((elem.text or "").strip())
                    if not text:
                        continue
                    cleaned_text = "\n".join(self.clean_message_lines(text.splitlines())).strip()
                    if not cleaned_text or cleaned_text in seen:
                        continue
                    seen.add(cleaned_text)
                    text_parts.append(cleaned_text)
            except Exception:
                continue

            if text_parts:
                break

        if not text_parts:
            try:
                # Fallback: usa o texto cru do container quando os spans mais específicos não existem.
                raw_text = self.normalize_text(
                    self.driver.execute_script("return arguments[0].innerText || arguments[0].textContent || '';", container)
                )
                if raw_text:
                    raw_lines = self.clean_message_lines(raw_text.splitlines())
                    if raw_lines:
                        cleaned_text = "\n".join(raw_lines).strip()
                        if cleaned_text:
                            return cleaned_text
            except Exception:
                pass

        return "\n".join(text_parts).strip() if text_parts else None

    def get_message_direction(self, container):
        # Separar mensagem recebida de enviada é essencial para o modo 4 não capturar respostas do próprio usuário.
        try:
            container_class = container.get_attribute("class") or ""
            if "message-in" in container_class:
                return "in"
            if "message-out" in container_class:
                return "out"
        except Exception:
            pass

        try:
            if container.find_elements(By.XPATH, "./ancestor::div[contains(@class,'message-in')]"):
                return "in"
            if container.find_elements(By.XPATH, "./ancestor::div[contains(@class,'message-out')]"):
                return "out"
        except Exception:
            pass

        try:
            outer_html = self.driver.execute_script("return arguments[0].outerHTML || '';", container) or ""
            if "message-in" in outer_html:
                return "in"
            if "message-out" in outer_html:
                return "out"
        except Exception:
            pass

        return None

    def extract_visible_time_from_container(self, container):
        time_pattern = re.compile(r"\d{1,2}:\d{2}")

        try:
            pre_plain = container.get_attribute("data-pre-plain-text") or ""
            match = time_pattern.search(pre_plain)
            if match:
                return match.group(0)
        except Exception:
            pass

        selectors = [
            ".//span[contains(@aria-label, ':')]",
            ".//span[contains(@class,'copyable-text')]",
            ".//span",
        ]
        for selector in selectors:
            try:
                for elem in container.find_elements(By.XPATH, selector):
                    text = self.normalize_text((elem.text or "").strip())
                    match = time_pattern.search(text or "")
                    if match:
                        return match.group(0)
            except Exception:
                continue

        return ""

    def extract_open_chat_contact_name(self):
        # Fecha um eventual painel lateral aberto antes de tentar identificar o nome do chat ativo.
        self.close_contact_info_panel_if_present()
        header = self.get_active_chat_header()
        if header is None:
            return None

        selectors = [
            ".//*[@data-testid='conversation-info-header-chat-title']",
            ".//span[@title]",
            ".//span[@dir='auto']",
        ]
        for selector in selectors:
            try:
                for elem in header.find_elements(By.XPATH, selector):
                    title = self.normalize_text((elem.get_attribute("title") or elem.text or "").strip())
                    if title and title.lower() not in {"menu"}:
                        return title
            except Exception:
                continue

        text = self.normalize_text((header.text or "").strip())
        return text.splitlines()[0].strip() if text else None

    def extract_last_message_text(self):
        """Read the latest visible message in the opened conversation."""
        message_containers = self.driver.find_elements(By.XPATH, "//div[@data-testid='msg-container']")
        for container in reversed(message_containers):
            try:
                combined = self.extract_message_text_from_container(container)
                if combined:
                    return combined
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        return None

    def build_live_message_external_id(self, direction, visible_time, body):
        normalized_body = self.normalize_text(body or "")
        raw = f"{direction}|{visible_time or ''}|{normalized_body}"
        return f"whatsapp_web_live:{sha1(raw.encode('utf-8')).hexdigest()[:32]}"

    def load_visible_chat_history(self, max_scrolls=12):
        """Ask WhatsApp Web to load older visible messages before syncing the chat."""
        stable_rounds = 0
        previous_count = 0
        for _ in range(max(1, max_scrolls)):
            try:
                containers = self.driver.find_elements(By.XPATH, "//div[@data-testid='msg-container']")
                current_count = len(containers)
                if current_count <= previous_count:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                previous_count = current_count
                if containers:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", containers[0])
                else:
                    self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.45)
                if stable_rounds >= 3:
                    break
            except Exception:
                break

        try:
            containers = self.driver.find_elements(By.XPATH, "//div[@data-testid='msg-container']")
            if containers:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'end'});", containers[-1])
                time.sleep(0.35)
        except Exception:
            pass

    def collect_visible_chat_messages(self, limit=120):
        """Collect the currently loaded WhatsApp Web conversation with direction and visible time."""
        messages = []
        containers = self.driver.find_elements(By.XPATH, "//div[@data-testid='msg-container']")
        for container in containers[-max(1, limit):]:
            try:
                body = self.extract_message_text_from_container(container)
                shared_contact = self.extract_shared_contact_from_container(container) or {}
                if not body and shared_contact.get("shared_contact_name"):
                    body = self.build_shared_contact_message_text(
                        shared_contact.get("shared_contact_name"),
                        shared_contact.get("shared_contact_phone") or "",
                    )
                direction = self.get_message_direction(container)
                if not body or direction not in {"in", "out"}:
                    continue
                visible_time = self.extract_visible_time_from_container(container)
                message_data = {
                    "direction": direction,
                    "body": self.normalize_text(body),
                    "visible_time": visible_time,
                    "timestamp": datetime.now().isoformat(),
                    "external_message_id": self.build_live_message_external_id(direction, visible_time, body),
                }
                if shared_contact.get("shared_contact_name"):
                    message_data["shared_contact_name"] = self.normalize_text(shared_contact.get("shared_contact_name") or "")
                if shared_contact.get("shared_contact_phone"):
                    message_data["shared_contact_phone"] = self.normalize_text(shared_contact.get("shared_contact_phone") or "")
                messages.append(message_data)
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        return messages

    def collect_recent_incoming_messages(self, contact_name, unread_count, phone_number, strict_incoming=False):
        """Collect up to unread_count latest incoming messages from the opened chat."""
        collected = []
        message_containers = self.driver.find_elements(By.XPATH, "//div[@data-testid='msg-container']")
        target_containers = []

        for container in message_containers:
            try:
                direction = self.get_message_direction(container)
                if direction == "out":
                    continue
                if direction == "in":
                    target_containers.append(container)
            except Exception:
                continue

        # No chat ativo usamos modo estrito para não cair em mensagens visíveis antigas quando a direção não puder ser inferida.
        if not target_containers and strict_incoming:
            return []

        if not target_containers:
            target_containers = message_containers

        for container in reversed(target_containers):
            try:
                combined = self.extract_message_text_from_container(container)
                shared_contact = self.extract_shared_contact_from_container(container) or {}
                if not combined and shared_contact.get("shared_contact_name"):
                    combined = self.build_shared_contact_message_text(
                        shared_contact.get("shared_contact_name"),
                        shared_contact.get("shared_contact_phone") or "",
                    )
                if not combined:
                    continue

                visible_time = self.extract_visible_time_from_container(container)
                normalized_combined = self.normalize_text(combined)
                if re.fullmatch(r"\d{1,2}:\d{2}", normalized_combined):
                    continue
                if visible_time and normalized_combined == visible_time:
                    continue

                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contact': contact_name,
                    'phone_number': phone_number or "",
                    'last_message': combined,
                    'message': combined,
                    'visible_time': visible_time,
                    'status': 'new'
                }
                if shared_contact.get("shared_contact_name"):
                    message_data["shared_contact_name"] = shared_contact.get("shared_contact_name")
                if shared_contact.get("shared_contact_phone"):
                    message_data["shared_contact_phone"] = shared_contact.get("shared_contact_phone")
                collected.append(message_data)
                if len(collected) >= max(1, unread_count):
                    break
            except Exception:
                continue

        collected.reverse()
        return collected

    def collect_active_chat_incoming_messages(self, contact_name, phone_number, limit=3):
        """Collect a small rolling window of incoming messages from the currently open chat."""
        collected = self.collect_recent_incoming_messages(
            contact_name,
            max(1, limit),
            phone_number,
            strict_incoming=True,
        )
        return collected[-limit:] if collected else []

    def process_active_open_chat_messages(self, bridge_only=False):
        """Detect new incoming messages in the chat that is already open, even without unread badge."""
        try:
            contact_name = self.extract_open_chat_contact_name()
            if not contact_name:
                return []
            if bridge_only and not self.is_bridge_tracked_contact(contact_name):
                return []

            message_batch = self.collect_active_chat_incoming_messages(contact_name, "", limit=3)
            if not message_batch:
                return []

            current_keys = [self.build_message_key(msg) for msg in message_batch]
            baseline = self.active_chat_baselines.get(contact_name)
            self.active_chat_baselines[contact_name] = current_keys[-20:]

            if baseline is None:
                # Na primeira passada apenas aprendemos o estado atual do chat aberto para evitar falso positivo.
                logging.info(f"Established active chat baseline for {contact_name}")
                return []

            unseen_candidates = [
                msg for msg in message_batch
                if self.build_message_key(msg) not in baseline
            ]
            if not unseen_candidates:
                return []

            self.enrich_shared_contact_details(contact_name, unseen_candidates)
            phone_number = self.extract_contact_number_from_open_chat(contact_name)
            self.close_contact_info_panel_if_present()
            new_messages = []
            for msg in unseen_candidates:
                msg['phone_number'] = phone_number or msg.get('phone_number', '')
                msg['status'] = 'active_chat_new'
                if self.register_message(msg):
                    new_messages.append(msg)

            if new_messages:
                self.unopened_messages = new_messages
                self.save_data()
                logging.info(f"Processed {len(new_messages)} new message(s) from active open chat: {contact_name}")

            return new_messages
        except Exception as e:
            logging.error(f"Error processing active open chat messages: {e}")
            return []

    def prime_active_chat_baseline(self, contact_name, phone_number=""):
        try:
            message_batch = self.collect_active_chat_incoming_messages(contact_name, phone_number, limit=5)
            baseline_keys = [self.build_message_key(msg) for msg in message_batch]
            self.active_chat_baselines[contact_name] = baseline_keys[-20:]
            logging.info(f"Primed active chat baseline for {contact_name} with {len(message_batch)} incoming message(s)")
        except Exception as e:
            logging.warning(f"Could not prime active chat baseline for {contact_name}: {e}")

    def collect_recent_reply_after_outbound(self, max_wait_seconds=12, poll_interval_seconds=1.5):
        outbound_context = self.last_outbound_chat if isinstance(self.last_outbound_chat, dict) else None
        if not outbound_context:
            return []

        contact_name = outbound_context.get("contact") or ""
        phone_number = outbound_context.get("phone_number") or ""
        conversation_id = outbound_context.get("conversation_id") or ""
        if not contact_name:
            return []

        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            time.sleep(poll_interval_seconds)
            active_contact = self.extract_open_chat_contact_name() or ""
            if self.normalize_contact_match_key(active_contact) != self.normalize_contact_match_key(contact_name):
                logging.info(
                    "Stopped waiting for immediate reply because the open chat changed from %s to %s",
                    contact_name,
                    active_contact or "unknown",
                )
                return []

            new_messages = self.process_active_open_chat_messages(bridge_only=False)
            if not new_messages:
                continue

            matched_messages = []
            for msg in new_messages:
                msg["phone_number"] = phone_number or msg.get("phone_number", "")
                if conversation_id:
                    msg["conversation_id"] = conversation_id
                matched_messages.append(msg)

            if matched_messages:
                logging.info(f"Captured {len(matched_messages)} immediate reply message(s) after outbound for {contact_name}")
                return matched_messages

        return []

    def extract_contact_number_from_open_chat(self, contact_name="Unknown"):
        """Try to read a phone number from the opened chat header or details pane."""
        phone_pattern = r"(?:\+\d{1,3}\s*)?(?:\(?\d{2,3}\)?\s*)?(?:9?\d{4}[-\s]?\d{4}|\d{3,4}[-\s]?\d{4,5})"

        def find_phone_number(text):
            if not text:
                return None

            match = re.search(phone_pattern, text)
            if not match:
                return None

            candidate = match.group().strip()
            digits_only = re.sub(r"\D", "", candidate)
            if len(digits_only) < 8:
                return None
            return candidate

        def log_strategy_result(strategy_name, candidate):
            if candidate:
                logging.info(f"Phone capture strategy '{strategy_name}' succeeded with: {candidate}")
            else:
                logging.info(f"Phone capture strategy '{strategy_name}' did not find a phone number")

        def find_phone_number_in_elements(elements):
            for elem in elements:
                try:
                    for raw_text in (
                        elem.get_attribute("title"),
                        elem.get_attribute("aria-label"),
                        elem.get_attribute("data-id"),
                        elem.get_attribute("href"),
                        elem.text,
                    ):
                        text = self.normalize_text((raw_text or "").strip())
                        candidate = find_phone_number(text)
                        if candidate:
                            return candidate
                except Exception:
                    continue
            return None

        def get_contact_info_panel_root():
            try:
                markers = self.driver.find_elements(
                    By.XPATH,
                    "//*[@data-testid='contact-info-header']"
                    " | //*[contains(normalize-space(.), 'Dados do contato')]"
                    " | //*[contains(normalize-space(.), 'Informações do contato')]"
                    " | //*[contains(normalize-space(.), 'Contact info')]"
                    " | //*[contains(normalize-space(.), 'Dados do grupo')]"
                    " | //*[contains(normalize-space(.), 'Group info')]"
                )
                if not markers:
                    return None

                viewport_width = self.driver.execute_script("return window.innerWidth;")
                best_panel = None
                best_area = -1

                for marker in markers:
                    try:
                        ancestors = marker.find_elements(By.XPATH, "ancestor::div")
                        for ancestor in ancestors:
                            size = ancestor.size
                            location = ancestor.location
                            if size["width"] < 220 or size["height"] < 220:
                                continue
                            if location["x"] < viewport_width * 0.6:
                                continue
                            area = size["width"] * size["height"]
                            if area > best_area:
                                best_area = area
                                best_panel = ancestor
                    except Exception:
                        continue

                return best_panel
            except Exception:
                return None

        def scan_visible_right_side():
            try:
                text = self.driver.execute_script(
                    """
                    const threshold = window.innerWidth * 0.62;
                    const nodes = Array.from(document.querySelectorAll('body *'));
                    const values = [];
                    for (const node of nodes) {
                        const rect = node.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) continue;
                        if (rect.left < threshold) continue;
                        const txt = (node.innerText || node.textContent || '').trim();
                        if (txt) values.push(txt);
                        for (const attr of ['title', 'aria-label', 'data-id', 'href']) {
                            const value = node.getAttribute && node.getAttribute(attr);
                            if (value) values.push(value);
                        }
                    }
                    return values.join('\\n');
                    """
                )
                text = self.normalize_text(text)
                return find_phone_number(text)
            except Exception:
                return None

        def scan_page_source():
            try:
                html = self.driver.execute_script("return document.body.outerHTML;")
                html = self.normalize_text(html)
                return find_phone_number(html)
            except Exception:
                return None

        def scan_contact_panel(panel):
            # Primeiro tentamos o texto renderizado; depois atributos e por fim um dump maior do DOM do painel.
            panel_text = self.normalize_text((panel.text or "").strip())
            candidate = find_phone_number(panel_text)
            if candidate:
                return candidate

            raw_panel_text = self.driver.execute_script("return arguments[0].innerText || arguments[0].textContent || '';", panel)
            raw_panel_text = self.normalize_text(raw_panel_text)
            candidate = find_phone_number(raw_panel_text)
            if candidate:
                return candidate

            detail_candidates = panel.find_elements(
                By.XPATH,
                ".//*[@title]"
                " | .//*[@aria-label]"
                " | .//*[@data-id]"
                " | .//a"
                " | .//span[@dir='auto']"
                " | .//div[contains(@class,'copyable-text')]"
            )
            candidate = find_phone_number_in_elements(detail_candidates)
            if candidate:
                return candidate

            dom_dump = self.driver.execute_script(
                """
                const root = arguments[0];
                const values = [];
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null);
                while (walker.nextNode()) {
                    const el = walker.currentNode;
                    for (const attr of ['title', 'aria-label', 'data-id', 'href']) {
                        const value = el.getAttribute && el.getAttribute(attr);
                        if (value) values.push(value);
                    }
                    if (el.innerText) values.push(el.innerText);
                    if (values.length > 600) break;
                }
                return values.join('\\n');
                """,
                panel
            )
            dom_dump = self.normalize_text(dom_dump)
            candidate = find_phone_number(dom_dump)
            if candidate:
                return candidate

            extra_panel_sections = panel.find_elements(
                By.XPATH,
                ".//section"
                " | .//div[@data-animate-dropdown-item='true']"
                " | .//div[contains(@class,'copyable-area')]"
                " | .//div[contains(@class,'x1n2onr6')]"
            )
            candidate = find_phone_number_in_elements(extra_panel_sections)
            if candidate:
                return candidate

            return None

        def open_contact_info_panel():
            chat_header = self.get_active_chat_header()
            if chat_header is None:
                return None

            def wait_for_contact_panel_root():
                def panel_ready(driver):
                    panel_root = get_contact_info_panel_root()
                    if panel_root is None:
                        return False
                    try:
                        size = panel_root.size
                        location = panel_root.location
                        viewport_width = driver.execute_script("return window.innerWidth;")
                        if size["width"] >= 220 and size["height"] >= 220 and location["x"] >= viewport_width * 0.6:
                            return panel_root
                    except Exception:
                        return False
                    return False

                return WebDriverWait(self.driver, 8).until(panel_ready)

            def close_schedule_call_modal_if_present():
                try:
                    modal = self.driver.find_elements(
                        By.XPATH,
                        "//*[contains(normalize-space(.), 'Programar ligação') or contains(normalize-space(.), 'Agendar ligação') or contains(normalize-space(.), 'Schedule call')]"
                    )
                    if not modal:
                        return

                    close_buttons = self.driver.find_elements(
                        By.XPATH,
                        "//div[@role='dialog']//button[@aria-label='Fechar']"
                        " | //div[@role='dialog']//button[@aria-label='Close']"
                        " | //div[@role='dialog']//*[@data-icon='x']/ancestor::button[1]"
                        " | //div[@role='dialog']//*[@data-testid='x']/ancestor::button[1]"
                    )
                    if close_buttons:
                        try:
                            close_buttons[0].click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", close_buttons[0])
                        time.sleep(0.4)
                except Exception:
                    pass

            clickable_selectors = [
                ".//span[@title]",
                ".//span[@dir='auto']",
                ".//img",
                ".//*[self::span or self::div][contains(@class,'copyable-text')]",
                ".//div[@role='button'][.//span[@title] or .//img]",
                ".//div[@role='button'][.//span[@dir='auto']]",
                ".//img/ancestor::div[@role='button'][1]",
                ".//div[contains(@class,'copyable-area')]",
                ".//*[@data-testid='conversation-info-header-chat-title']",
            ]

            for selector in clickable_selectors:
                try:
                    header_candidates = chat_header.find_elements(By.XPATH, selector)
                    if not header_candidates:
                        continue
                    header_button = header_candidates[0]
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", header_button)
                    time.sleep(0.2)
                    try:
                        header_button.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", header_button)

                    panel = wait_for_contact_panel_root()
                    if panel:
                        return panel
                except Exception:
                    # Se o clique abriu um modal paralelo, tentamos limpá-lo e seguir para o próximo caminho.
                    close_schedule_call_modal_if_present()
                    continue

            menu_button_selectors = [
                ".//button[@aria-label='Menu']",
                ".//button[@title='Menu']",
                ".//*[@role='button'][@aria-label='Menu']",
                ".//span[@data-icon='menu']/ancestor::*[@role='button'][1]",
                ".//span[@data-testid='menu']/ancestor::*[@role='button'][1]",
                ".//div[@role='button'][.//span[@data-icon='menu'] or .//span[@data-testid='menu']]",
            ]

            info_option_selectors = [
                "//div[@role='menu']//*[self::div or self::span][contains(., 'Dados do contato')]",
                "//div[@role='menu']//*[self::div or self::span][contains(., 'Informações do contato')]",
                "//div[@role='menu']//*[self::div or self::span][contains(., 'Contact info')]",
                "//div[@role='menu']//*[self::div or self::span][contains(., 'Dados do grupo')]",
                "//div[@role='menu']//*[self::div or self::span][contains(., 'Group info')]",
                "//div[@role='application']//*[self::div or self::span][contains(., 'Dados do contato')]",
                "//div[@role='application']//*[self::div or self::span][contains(., 'Informações do contato')]",
                "//div[@role='application']//*[self::div or self::span][contains(., 'Contact info')]",
                "//div[@role='application']//*[self::div or self::span][contains(., 'Dados do grupo')]",
                "//div[@role='application']//*[self::div or self::span][contains(., 'Group info')]",
            ]

            for selector in menu_button_selectors:
                try:
                    menu_candidates = chat_header.find_elements(By.XPATH, selector)
                    if not menu_candidates:
                        continue
                    menu_button = menu_candidates[0]
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", menu_button)
                    time.sleep(0.2)
                    try:
                        menu_button.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", menu_button)
                    time.sleep(0.5)
                    close_schedule_call_modal_if_present()

                    for option_selector in info_option_selectors:
                        try:
                            info_option = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.XPATH, option_selector))
                            )
                            try:
                                info_option.click()
                            except Exception:
                                self.driver.execute_script("arguments[0].click();", info_option)

                            panel = wait_for_contact_panel_root()
                            return panel
                        except Exception:
                            continue
                except Exception:
                    continue

            return None

        try:
            header_candidates = self.driver.find_elements(
                By.XPATH,
                "//header//*[@title] | //header//*[@aria-label] | //header//*[@data-id] | //header//a | //header//span[@dir='auto'] | //header//div[@role='button']"
            )
            candidate = find_phone_number_in_elements(header_candidates)
            if candidate:
                self.clear_phone_capture_debug()
                return candidate
        except Exception:
            pass

        try:
            panel = open_contact_info_panel()
            if panel is None:
                logging.info("Could not open contact info panel from chat header")
                self.save_phone_capture_debug(contact_name, "", "Could not open contact info panel from chat header")
                self.save_contact_panel_artifacts(contact_name)
                return None
            time.sleep(1)
            panel_root = get_contact_info_panel_root() or panel

            candidate = scan_contact_panel(panel_root)
            log_strategy_result("panel_root_scan", candidate)
            if candidate:
                self.clear_phone_capture_debug()
                return candidate

            self.driver.execute_script("arguments[0].scrollTop = 0;", panel_root)
            time.sleep(0.3)
            for _ in range(10):
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", panel_root)
                time.sleep(0.6)
                candidate = scan_contact_panel(panel_root)
                if candidate:
                    log_strategy_result("panel_scroll_scan", candidate)
                    self.clear_phone_capture_debug()
                    return candidate

            candidate = scan_visible_right_side()
            log_strategy_result("visible_right_side_scan", candidate)
            if candidate:
                self.clear_phone_capture_debug()
                return candidate

            candidate = scan_page_source()
            log_strategy_result("page_source_scan", candidate)
            if candidate:
                self.clear_phone_capture_debug()
                return candidate

            raw_panel_text = self.normalize_text(
                self.driver.execute_script("return arguments[0].innerText || arguments[0].textContent || '';", panel_root)
            )
            logging.info(f"Contact info panel did not expose a phone number. Panel preview: {raw_panel_text[:300]!r}")
            self.save_phone_capture_debug(contact_name, raw_panel_text, "Contact info panel did not expose a phone number")
            self.save_contact_panel_body_artifacts(contact_name, panel_root)
        except Exception as e:
            logging.info(f"Failed while reading contact info panel for phone number: {e}")
            self.save_phone_capture_debug(contact_name, "", f"Failed while reading contact info panel for phone number: {e}")
            self.save_contact_panel_artifacts(contact_name)
        finally:
            try:
                if not self.close_contact_info_panel_if_present():
                    close_button = self.driver.find_element(
                        By.XPATH,
                        "//button[@aria-label='Close']"
                        " | //button[@aria-label='Fechar']"
                        " | //span[@data-testid='x']"
                        " | //div[@role='button' and @aria-label='Close']"
                        " | //div[@role='button' and @aria-label='Fechar']"
                    )
                    self.driver.execute_script("arguments[0].click();", close_button)
                    time.sleep(0.5)
            except Exception:
                pass

        return None

    def normalize_phone_number(self, phone_number):
        digits_only = re.sub(r"\D", "", phone_number or "")
        if not digits_only:
            raise ValueError("Invalid phone number")
        return digits_only

    def ensure_whatsapp_ready(self):
        # Tenta reutilizar a sessão existente e só pede QR quando realmente necessário.
        self.open_url_with_retries("https://web.whatsapp.com", timeout=90, retries=3)
        wait = WebDriverWait(self.driver, 60)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))
            logging.info("WhatsApp Web session is already authenticated")
            return
        except TimeoutException:
            logging.info("WhatsApp Web is not authenticated yet")

        input("Escaneie o QR code e pressione Enter...")
        self.open_url_with_retries("https://web.whatsapp.com", timeout=90, retries=2)
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

    def wait_for_message_in_chat(self, expected_message):
        normalized_expected = self.normalize_text(expected_message)

        def message_visible(driver):
            try:
                outgoing_messages = driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class,'message-out')]//div[contains(@class,'copyable-text')]"
                )
                for message in reversed(outgoing_messages):
                    text = self.normalize_text(message.text or "")
                    if text and normalized_expected in text:
                        return True
            except Exception:
                return False
            return False

        WebDriverWait(self.driver, 15).until(message_visible)

    def composer_contains_text(self, send_box, expected_message):
        try:
            composer_text = self.normalize_text(send_box.text or "")
            return bool(composer_text and self.normalize_text(expected_message) in composer_text)
        except Exception:
            return False

    def click_send_button(self, wait, send_box):
        try:
            # O botão de enviar muda de estrutura com frequência; por isso usamos vários caminhos até ele.
            send_button = wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//footer//button[.//span[@data-icon='send'] or .//span[@data-testid='send']]"
                " | //footer//*[@role='button'][.//span[@data-icon='send'] or .//span[@data-testid='send']]"
                " | //footer//span[@data-icon='send']/ancestor::*[@role='button'][1]"
                " | //footer//span[@data-testid='send']/ancestor::*[@role='button'][1]"
            )))
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", send_button)
            time.sleep(0.7)
            try:
                send_button.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", send_button)
            return True
        except Exception:
            send_box.click()
            send_box.send_keys(Keys.ENTER)
            return False

    def prepare_bridge_outbox_with_live_context(self, item, body):
        phone_number = item.get("phone_number")
        outbox_id = item.get("id")
        if not phone_number or not outbox_id:
            return None

        normalized_phone = self.normalize_phone_number(phone_number)
        self.open_url_with_retries(f"https://web.whatsapp.com/send?phone={normalized_phone}", timeout=90, retries=3)
        self.ensure_chat_available_for_phone(phone_number, timeout=40)
        time.sleep(1.2)

        self.load_visible_chat_history(max_scrolls=12)
        contact_name = self.extract_open_chat_contact_name() or phone_number
        live_messages = self.collect_visible_chat_messages(limit=120)
        logging.info("Bridge live sync captured %s visible message(s) for %s", len(live_messages), contact_name)

        sync_response = self.sync_bridge_live_conversation(item, live_messages, contact_name=contact_name)
        logging.info(
            "Bridge live sync for %s: inserted=%s skipped=%s total=%s",
            contact_name,
            sync_response.get("inserted"),
            sync_response.get("skipped"),
            sync_response.get("total_received"),
        )

        review = self.review_bridge_live_send_gate(item, body, live_messages)
        decision = str(review.get("decision") or "").strip().lower()
        gate = review.get("gate") if isinstance(review.get("gate"), dict) else {}
        facts = gate.get("facts") if isinstance(gate.get("facts"), dict) else {}
        logging.info(
            "Bridge live send gate for %s: decision=%s reason=%s live_total=%s db_sent=%s db_inbound=%s",
            contact_name,
            decision or "unknown",
            gate.get("reason") or review.get("reason") or "",
            facts.get("total_live_messages"),
            facts.get("db_sent_outbound_count"),
            facts.get("db_inbound_count"),
        )
        if decision != "send":
            self.remember_local_bridge_hold(item.get("id"), review)
            return None

        return {
            "body": self.normalize_text(review.get("body") or body),
            "contact_name": contact_name,
        }

    def send_message_to_number(self, phone_number, message_text):
        """Open a direct chat and send a message."""
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "contact": phone_number,
            "phone_number": phone_number,
            "last_message": self.normalize_text(message_text),
            "status": "failed"
        }
        try:
            normalized_phone = self.normalize_phone_number(phone_number)
            normalized_message = self.normalize_text(message_text)

            self.open_url_with_retries(f"https://web.whatsapp.com/send?phone={normalized_phone}", timeout=90, retries=3)

            wait = WebDriverWait(self.driver, 40)
            send_box = self.ensure_chat_available_for_phone(phone_number, timeout=40)
            time.sleep(1.2)

            current_box_text = self.normalize_text(send_box.text or "")
            send_box.click()
            if current_box_text:
                send_box.send_keys(Keys.CONTROL + "a")
                send_box.send_keys(Keys.BACKSPACE)
                time.sleep(0.2)
            send_box.send_keys(normalized_message)

            sent = False
            for attempt in range(3):
                # O envio usa retry porque o WhatsApp Web às vezes digita o texto, mas demora para confirmar o clique.
                logging.info(f"Send attempt {attempt + 1} for {phone_number}")
                try:
                    send_box = wait.until(EC.element_to_be_clickable((By.XPATH, "//footer//div[@contenteditable='true']")))
                except Exception:
                    pass
                used_button = self.click_send_button(wait, send_box)

                try:
                    self.wait_for_message_in_chat(normalized_message)
                    sent = True
                    break
                except Exception:
                    logging.warning(f"Message not confirmed after attempt {attempt + 1}")

                if self.composer_contains_text(send_box, normalized_message):
                    try:
                        send_box.click()
                        send_box.send_keys(Keys.ENTER)
                    except Exception:
                        pass

                    try:
                        self.driver.execute_script(
                            """
                            const el = arguments[0];
                            el.focus();
                            el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', which: 13, keyCode: 13, bubbles: true}));
                            el.dispatchEvent(new KeyboardEvent('keypress', {key: 'Enter', code: 'Enter', which: 13, keyCode: 13, bubbles: true}));
                            el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', which: 13, keyCode: 13, bubbles: true}));
                            """,
                            send_box
                        )
                    except Exception:
                        pass

                time.sleep(1.0 if used_button else 1.5)

            if not sent:
                raise TimeoutException("Message was typed but not confirmed as sent")

            history_entry["status"] = "sent"
            history_entry["timestamp"] = datetime.now().isoformat()
            try:
                history_entry["chat_contact"] = self.extract_open_chat_contact_name() or normalized_phone
            except Exception:
                history_entry["chat_contact"] = normalized_phone
            self.prime_active_chat_baseline(history_entry["chat_contact"], normalized_phone)
            self.append_sent_message_history(history_entry)
            logging.info(f"Message sent to {phone_number}")
            return history_entry
        except WhatsAppNumberUnavailableError as e:
            history_entry["error"] = str(e)
            history_entry["timestamp"] = datetime.now().isoformat()
            self.append_sent_message_history(history_entry)
            logging.warning(f"WhatsApp unavailable for {phone_number}: {e}")
            raise
        except Exception as e:
            history_entry["error"] = str(e)
            history_entry["timestamp"] = datetime.now().isoformat()
            self.append_sent_message_history(history_entry)
            logging.error(f"Error sending message to {phone_number}: {e}")
            return None
    
    def get_single_unopened_message(self, conversation_info):
        """Open one unread conversation and save its latest message and number."""
        try:
            wait = WebDriverWait(self.driver, 20)
            opened = self.open_unread_conversation(conversation_info)
            if not opened:
                logging.error("Unread conversation could not be opened")
                return None

            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='conversation-panel-body'] | //footer")))

            last_text = self.extract_last_message_text()
            if not last_text:
                self.save_message_capture_artifacts(
                    conversation_info.get('contact', 'unknown'),
                    "No readable message text found in opened chat"
                )
                raise NoSuchElementException("No readable message text found in opened chat")

            phone_number = self.extract_contact_number_from_open_chat(conversation_info['contact'])
            message_batch = self.collect_recent_incoming_messages(
                conversation_info['contact'],
                conversation_info['unread_count'],
                phone_number,
            )
            if not message_batch:
                message_batch = [{
                    'timestamp': datetime.now().isoformat(),
                    'contact': conversation_info['contact'],
                    'phone_number': phone_number or "",
                    'last_message': last_text,
                    'message': last_text,
                    'visible_time': "",
                    'unread_count': conversation_info['unread_count'],
                    'status': 'new'
                }]
            else:
                self.enrich_shared_contact_details(conversation_info['contact'], message_batch)

            for item in message_batch:
                item['unread_count'] = conversation_info['unread_count']

            latest_captured_text = self.normalize_text((message_batch[-1].get('message') or message_batch[-1].get('last_message') or last_text).strip())
            logging.info(f"Latest message from {conversation_info['contact']}: {latest_captured_text}")
            logging.info(f"Detected phone number: {phone_number or 'not found'}")
            return message_batch
        except Exception as e:
            logging.error(f"Error getting message from {conversation_info.get('contact', 'unknown')}: {e}")
            return None
    
    def process_unopened_messages(self):
        """Process only one unread conversation."""
        try:
            self.load_data(silent=True)
            
            wait = WebDriverWait(self.driver, 60)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))
            
            conversation = self.find_first_unopened_conversation()
            if not conversation:
                logging.info("No valid unread conversation found")
                return []

            messages = self.get_single_unopened_message(conversation)
            if not messages:
                return []

            new_messages = []
            for msg in messages:
                if self.register_message(msg):
                    new_messages.append(msg)

            if not new_messages:
                logging.info("No new unread messages to persist")
                return []

            self.unopened_messages = new_messages
            
            self.save_data()
            logging.info(f"Processed {len(new_messages)} unread message(s)")
            return new_messages
            
        except Exception as e:
            logging.error(f"Error processing unopened messages: {e}")
            return []

    def process_all_unopened_messages(self, verbose=True, conversations=None):
        """Process every unread conversation and collect all newly received messages."""
        try:
            self.load_data(silent=True)

            wait = WebDriverWait(self.driver, 60)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

            target_conversations = conversations if conversations is not None else self.find_all_unopened_conversations(verbose=verbose)
            if not target_conversations:
                if verbose:
                    logging.info("No unread conversations to process")
                return []

            new_messages = []
            for conversation in target_conversations:
                # Processa cada conversa separadamente porque abrir um chat altera a própria lista de não lidas.
                message_batch = self.get_single_unopened_message(conversation)
                if not message_batch:
                    continue
                for msg in message_batch:
                    if self.register_message(msg):
                        new_messages.append(msg)

            if not new_messages:
                if verbose:
                    logging.info("Unread conversations found, but no unseen messages were captured")
                return []

            self.unopened_messages = new_messages
            self.save_data()
            logging.info(f"Processed {len(new_messages)} total new message(s) from all unread conversations")
            return new_messages
        except Exception as e:
            logging.error(f"Error processing all unread messages: {e}")
            return []

    def monitor_all_incoming_messages(self, poll_seconds=4):
        """Continuously monitor all unread conversations and capture every new arrival."""
        try:
            self.load_data()
            self.ensure_whatsapp_ready()
            print("\n=== CONTINUOUS MONITOR ===")
            print("Monitorando todas as mensagens recebidas. Pressione Ctrl+C para parar.")
            archived_only_logged = False

            while True:
                loop_messages = []

                # Primeiro olhamos a sidebar; depois complementamos com a conversa já aberta.
                conversations = self.find_all_unopened_conversations(verbose=False)
                if not conversations:
                    unread_count = 0
                    try:
                        unread_count = self.count_visible_unread_candidates()
                    except Exception:
                        pass

                    if unread_count > 0:
                        if not archived_only_logged:
                            logging.info("Only 'Arquivadas' remains unread; waiting for a real conversation")
                            archived_only_logged = True
                    else:
                        archived_only_logged = False

                    active_messages = self.process_active_open_chat_messages()
                    if active_messages:
                        loop_messages.extend(active_messages)
                else:
                    archived_only_logged = False
                    unread_messages = self.process_all_unopened_messages(verbose=False)
                    if unread_messages:
                        loop_messages.extend(unread_messages)

                    active_messages = self.process_active_open_chat_messages()
                    if active_messages:
                        loop_messages.extend(active_messages)

                if loop_messages:
                    unique_messages = []
                    seen_keys = set()
                    for msg in loop_messages:
                        # Evita imprimir duas vezes o mesmo item quando ele apareceu tanto na sidebar quanto no chat ativo.
                        key = self.build_message_key(msg)
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        unique_messages.append(msg)

                    print(f"\n=== NEW MESSAGES ({len(unique_messages)}) ===")
                    for i, msg in enumerate(unique_messages, 1):
                        print(f"\n{i}. Contact: {msg['contact']}")
                        print(f"   Phone: {msg['phone_number'] or 'Not found'}")
                        print(f"   Message: {msg['last_message']}")
                        print(f"   Time: {msg['timestamp']}")
                time.sleep(poll_seconds)
        except KeyboardInterrupt:
            logging.info("Continuous monitor stopped by user")
        finally:
            if self.driver is not None:
                self.driver.quit()
            logging.info("Chrome driver closed")

    def collect_new_incoming_loop_messages(self):
        loop_messages = []
        conversations = self.find_all_unopened_conversations(verbose=False)
        if not conversations:
            unread_count = 0
            try:
                unread_count = self.count_visible_unread_candidates()
            except Exception:
                pass

            if unread_count > 0:
                logging.info("Unread conversations are visible, but none could be resolved from the sidebar yet")

            active_messages = self.process_active_open_chat_messages(bridge_only=True)
            if active_messages:
                loop_messages.extend(active_messages)
        else:
            logging.info(
                "Bridge will inspect %s unread conversation(s): %s",
                len(conversations),
                ", ".join(conversation.get("contact", "Unknown") for conversation in conversations),
            )
            unread_messages = self.process_all_unopened_messages(verbose=False, conversations=conversations)
            if unread_messages:
                loop_messages.extend(unread_messages)

            active_messages = self.process_active_open_chat_messages(bridge_only=True)
            if active_messages:
                loop_messages.extend(active_messages)

        unique_messages = []
        seen_keys = set()
        for msg in loop_messages:
            key = self.build_message_key(msg)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_messages.append(msg)
        return unique_messages

    def sync_bridge_inbound_messages(self, inbound_messages, log_prefix="Bridge inbound synced"):
        synced_count = 0
        for message_data in inbound_messages:
            try:
                response = self.forward_bridge_incoming_message(message_data)
                response_status = response.get("status") if isinstance(response, dict) else "ok"
                if response_status == "ignored_unmapped":
                    logging.info("Bridge inbound ignored: %s", message_data.get("contact"))
                else:
                    logging.info("%s: %s (%s)", log_prefix, message_data.get("contact"), response_status)
                    synced_count += 1
            except Exception as e:
                logging.error(f"Bridge inbound sync failed for {message_data.get('contact')}: {e}")
        return synced_count

    def flush_bridge_outbound_once_with_immediate_reply(self, limit=3):
        outbound_results = self.process_bridge_outbox_once(limit=limit)
        for item in outbound_results:
            logging.info(f"Bridge outbound {item['status']}: {item['phone_number']}")

        immediate_reply_messages = self.collect_recent_reply_after_outbound()
        if immediate_reply_messages:
            self.sync_bridge_inbound_messages(
                immediate_reply_messages,
                log_prefix="Bridge inbound synced immediately after outbound",
            )
        self.last_outbound_chat = None
        return outbound_results

    def process_bridge_unread_conversations_immediately(self):
        try:
            self.load_data(silent=True)

            wait = WebDriverWait(self.driver, 60)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

            conversations = self.find_all_unopened_conversations(verbose=False)
            if not conversations:
                return 0

            logging.info(
                "Bridge will inspect %s unread conversation(s): %s",
                len(conversations),
                ", ".join(conversation.get("contact", "Unknown") for conversation in conversations),
            )

            total_synced = 0
            for conversation in conversations:
                message_batch = self.get_single_unopened_message(conversation)
                if not message_batch:
                    continue

                new_messages = []
                for msg in message_batch:
                    if self.register_message(msg):
                        new_messages.append(msg)

                if not new_messages:
                    continue

                self.unopened_messages = new_messages
                self.save_data()
                logging.info(
                    "Processed %s new unread message(s) for %s",
                    len(new_messages),
                    conversation.get("contact", "Unknown"),
                )

                total_synced += self.sync_bridge_inbound_messages(new_messages)
                # Assim que uma conversa nova entra, respondemos antes de abrir a proxima.
                self.flush_bridge_outbound_once_with_immediate_reply(limit=3)

            return total_synced
        except Exception as e:
            logging.error(f"Error processing unread conversations with immediate bridge response: {e}")
            return 0

    def run_bridge_loop(self):
        lock_path = Path("whatsapp_bridge.lock")
        lock_fd = None
        try:
            try:
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(lock_fd, str(os.getpid()).encode("utf-8"))
            except FileExistsError:
                existing_pid = ""
                try:
                    existing_pid = lock_path.read_text(encoding="utf-8").strip()
                except OSError:
                    existing_pid = ""
                if existing_pid and is_process_alive(existing_pid):
                    logging.warning("WhatsApp Web bridge ja esta rodando no processo %s. Encerrando esta instancia.", existing_pid)
                    return
                try:
                    lock_path.unlink()
                except OSError:
                    logging.warning("Nao foi possivel remover lock antigo do bridge. Encerrando para evitar duplicidade.")
                    return
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(lock_fd, str(os.getpid()).encode("utf-8"))

            self.load_data()
            startup_ok = False
            for startup_attempt in range(1, 4):
                try:
                    self.ensure_whatsapp_ready()
                    startup_ok = True
                    break
                except Exception as e:
                    logging.warning("Bridge startup attempt %s failed: %s", startup_attempt, e)
                    if startup_attempt >= 3:
                        raise
                    self.restart_driver_session()
                    time.sleep(3)
            if not startup_ok:
                raise RuntimeError("Nao foi possivel iniciar o WhatsApp Web bridge.")
            print("\n=== WHATSAPP WEB BRIDGE ===")
            print("Bridge ativo entre Selenium local e ClinicFlux AI. Pressione Ctrl+C para parar.")

            while True:
                try:
                    immediate_reply_messages = self.collect_recent_reply_after_outbound()
                    if immediate_reply_messages:
                        self.sync_bridge_inbound_messages(
                            immediate_reply_messages,
                            log_prefix="Bridge inbound synced immediately after outbound",
                        )
                    self.last_outbound_chat = None

                    unread_synced = self.process_bridge_unread_conversations_immediately()
                    if unread_synced:
                        logging.info(
                            "Bridge prioritized %s newly read inbound conversation(s) before older outbound pendings",
                            unread_synced,
                        )
                    else:
                        inbound_messages = self.collect_new_incoming_loop_messages()
                        synced_count = self.sync_bridge_inbound_messages(inbound_messages)
                        if synced_count:
                            logging.info(
                                "Bridge prioritized %s newly synced inbound conversation(s) before older outbound pendings",
                                synced_count,
                            )
                            self.flush_bridge_outbound_once_with_immediate_reply(limit=3)
                        else:
                            # Escaneamos alguns itens por ciclo para nao travar a fila inteira em um unico hold.
                            self.flush_bridge_outbound_once_with_immediate_reply(limit=3)

                    time.sleep(self.bridge_poll_seconds)
                except Exception as e:
                    logging.error(f"Bridge loop iteration failed: {e}")
                    time.sleep(max(2, self.bridge_poll_seconds))
        except KeyboardInterrupt:
            logging.info("WhatsApp Web bridge stopped by user")
        finally:
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
                try:
                    lock_path.unlink()
                except OSError:
                    pass
            self.driver.quit()
            logging.info("Chrome driver closed")

    def process_last_conversation_message(self):
        """Process the last visible conversation from the sidebar."""
        try:
            self.load_data(silent=True)

            wait = WebDriverWait(self.driver, 60)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

            conversation = self.find_last_conversation()
            if not conversation:
                logging.info("No visible conversation found")
                return []

            opened = self.open_conversation_from_sidebar(conversation)
            if not opened:
                logging.error("Last conversation could not be opened")
                return []

            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='conversation-panel-body'] | //footer")))

            last_text = self.extract_last_message_text()
            if not last_text:
                self.save_message_capture_artifacts(
                    conversation.get('contact', 'unknown'),
                    "No readable message text found in opened chat"
                )
                raise NoSuchElementException("No readable message text found in opened chat")

            phone_number = self.extract_contact_number_from_open_chat(conversation['contact'])
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contact': conversation['contact'],
                'phone_number': phone_number or "",
                'last_message': last_text,
                'unread_count': 0,
                'status': 'last_conversation'
            }

            self.message_history.append(message_data)
            self.unopened_messages = [message_data]
            self.save_data()
            logging.info("Processed last visible conversation")
            return [message_data]
        except Exception as e:
            logging.error(f"Error processing last conversation: {e}")
            return []
    
    def monitor_new_conversations(self, capture_mode="unopened"):
        """Capture data from unread or last visible conversation."""
        try:
            self.load_data()
            self.ensure_whatsapp_ready()

            if capture_mode == "last":
                messages = self.process_last_conversation_message()
                header = "=== LAST CONVERSATION ==="
                empty_text = "No visible conversations found."
            else:
                messages = self.process_unopened_messages()
                header = "=== UNOPENED CONVERSATIONS ==="
                empty_text = "No unopened conversations found."

            print(f"\n{header}")
            if not messages:
                print(empty_text)
            else:
                for i, msg in enumerate(messages, 1):
                    print(f"\n{i}. Contact: {msg['contact']}")
                    print(f"   Phone: {msg['phone_number'] or 'Not found'}")
                    print(f"   Last message: {msg['last_message']}")
                    print(f"   Time: {msg['timestamp']}")
                
                with open('unopened_conversations.txt', 'w', encoding='utf-8-sig') as f:
                    f.write("=== UNOPENED CONVERSATIONS ===\n\n")
                    for i, msg in enumerate(messages, 1):
                        f.write(f"{i}. Contact: {msg['contact']}\n")
                        f.write(f"   Phone: {msg['phone_number'] or 'Not found'}\n")
                        f.write(f"   Last message: {msg['last_message']}\n")
                        f.write(f"   Time: {msg['timestamp']}\n\n")
                
                logging.info("Unopened conversations saved to file")
            
        except Exception as e:
            logging.error(f"Error in monitor_new_conversations: {e}")
            self.restart_session()
    
    def restart_session(self):
        """Restart the session"""
        logging.info("Restarting session...")
        try:
            self.driver.quit()
        except:
            pass
        self.setup_driver()
        self.monitor_new_conversations()
    
    def run(self):
        """Main execution loop"""
        try:
            self.monitor_new_conversations()
        except KeyboardInterrupt:
            logging.info("Session terminated by user")
        finally:
            self.driver.quit()
            logging.info("Chrome driver closed")

if __name__ == "__main__":
    whatsapp = WhatsAppAutomation()
    default_test_number = os.getenv("WHATSAPP_WEB_TEST_NUMBER", "")
    default_test_message = "Olá! Esta é uma mensagem de teste enviada pelo WhatsApp Web."

    mode = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if not mode:
        chosen = input("Digite '1' para ler conversa não aberta, '2' para enviar mensagem de teste, '3' para pegar a última conversa, '4' para monitorar tudo ou '5' para integrar com o sistema: ").strip()
        if chosen == "2":
            mode = "send"
        elif chosen == "3":
            mode = "last"
        elif chosen == "4":
            mode = "monitor_all"
        elif chosen == "5":
            mode = "bridge"
        else:
            mode = "read"

    if mode == "send":
        try:
            whatsapp.ensure_whatsapp_ready()
            first_loop = True
            while True:
                target_number = default_test_number
                target_message = default_test_message

                if first_loop and len(sys.argv) > 2:
                    target_number = sys.argv[2]
                else:
                    typed_number = input(f"Número destino [{default_test_number}]: ").strip()
                    if typed_number:
                        target_number = typed_number

                if first_loop and len(sys.argv) > 3:
                    target_message = " ".join(sys.argv[3:])
                else:
                    typed_message = input(f"Mensagem [{default_test_message}]: ").strip()
                    if typed_message:
                        target_message = typed_message

                result = whatsapp.send_message_to_number(target_number, target_message)
                if result:
                    print("\n=== MESSAGE SENT ===")
                    print(f"Contact: {result['contact']}")
                    print(f"Phone: {result['phone_number']}")
                    print(f"Message: {result['last_message']}")
                    print(f"Time: {result['timestamp']}")
                    print(f"Status: {result['status']}")
                else:
                    print("\n=== MESSAGE FAILED ===")
                    print("Veja sent_messages_history.json para o registro da falha.")

                next_action = input("\nDigite '1' para enviar msg2 ou '2' para fechar: ").strip()
                if next_action != "1":
                    break

                first_loop = False
        finally:
            whatsapp.driver.quit()
            logging.info("Chrome driver closed")
    elif mode == "monitor_all":
        whatsapp.monitor_all_incoming_messages()
    elif mode == "bridge":
        whatsapp.run_bridge_loop()
    else:
        whatsapp.monitor_new_conversations("last" if mode == "last" else "unopened")
        whatsapp.driver.quit()
        logging.info("Chrome driver closed")
