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
from urllib.parse import quote
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WhatsAppAutomation:
    def __init__(self):
        self.driver = None
        self.message_history = []
        self.unopened_messages = []
        self.sent_messages_history = []
        # Baseline do chat aberto para detectar novas mensagens sem depender do badge de não lidas.
        self.processed_message_keys = set()
        self.active_chat_baselines = {}
        self.setup_driver()
        
    def setup_driver(self):
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=WebRtcHideLocalIpsWithMdns')
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        options.add_argument('--start-maximized')
        # Mantem a sessão do WhatsApp Web entre execuções para evitar novo QR a cada teste.
        try:
            profile_dir = os.path.join(os.getcwd(), 'chrome_profile')
            os.makedirs(profile_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={profile_dir}")
            options.add_argument('--profile-directory=Default')
            # Pequenos ajustes para reduzir atrito com a detecção de automação do navegador.
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
        except Exception as e:
            logging.warning(f"Could not set profile dir: {e}")

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)
        logging.info(f"Chrome driver initialized successfully (profile: {os.path.abspath('chrome_profile')})")
        
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
    
    def load_data(self):
        """Load data from JSON files"""
        try:
            # O histórico é usado também como proteção contra duplicatas no monitor contínuo.
            if os.path.exists('message_history.json'):
                with open('message_history.json', 'r', encoding='utf-8-sig') as f:
                    self.message_history = json.load(f)
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
                logging.info("Unopened messages loaded")

            # Load sent messages history
            if os.path.exists('sent_messages_history.json'):
                with open('sent_messages_history.json', 'r', encoding='utf-8-sig') as f:
                    self.sent_messages_history = json.load(f)
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
        self.load_data()
        self.sent_messages_history.append(entry)
        self.save_data()

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
                ".//span[@data-testid='icon-unread-count'] | .//span[contains(@aria-label, 'unread')]",
            )
            count_text = unread_elem.text.strip()
            return int(count_text) if count_text.isdigit() else 1
        except Exception:
            return 1

    def find_all_unopened_conversations(self, verbose=True):
        """Return all valid unread conversations currently visible."""
        try:
            wait = WebDriverWait(self.driver, 30)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

            unread_chats = self.driver.find_elements(
                By.XPATH,
                "//div[@data-testid='cell-frame-container'][.//span[@data-testid='icon-unread-count'] or .//span[contains(@aria-label, 'unread')]]",
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
                "//div[@data-testid='cell-frame-container'][.//span[@data-testid='icon-unread-count'] or .//span[contains(@aria-label, 'unread')]]",
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
        normalized_contact = re.sub(r"\s+", " ", contact_name).strip().lower()

        def chat_opened(driver):
            try:
                header_candidates = driver.find_elements(
                    By.XPATH,
                    "//header//span[@title] | //header//*[@title] | //header//span[@dir='auto']"
                )
                for elem in header_candidates:
                    text = ((elem.get_attribute("title") or elem.text) or "").strip()
                    normalized_text = re.sub(r"\s+", " ", text).strip().lower()
                    if normalized_text and normalized_contact in normalized_text:
                        return True
            except Exception:
                return False
            return False

        WebDriverWait(self.driver, 15).until(chat_opened)

    def open_unread_conversation(self, conversation_info):
        """Open the unread conversation by title, with index fallback and retries."""
        wait = WebDriverWait(self.driver, 20)
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))
        normalized_contact = re.sub(r"\s+", " ", conversation_info['contact']).strip().lower()

        for attempt in range(3):
            try:
                # Rebusca os elementos a cada tentativa porque a sidebar muda bastante após novas mensagens.
                unread_chats = self.driver.find_elements(
                    By.XPATH,
                    "//div[@data-testid='cell-frame-container'][.//span[@data-testid='icon-unread-count'] or .//span[contains(@aria-label, 'unread')]]",
                )

                target = None
                for elem in unread_chats:
                    try:
                        candidate = self.extract_contact_name(elem)
                        normalized_candidate = re.sub(r"\s+", " ", candidate).strip().lower()
                        if normalized_candidate == normalized_contact:
                            target = elem
                            break
                    except StaleElementReferenceException:
                        continue

                if target is None and conversation_info['index'] < len(unread_chats):
                    target = unread_chats[conversation_info['index']]

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
                    if not text or text in seen:
                        continue
                    seen.add(text)
                    text_parts.append(text)
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
                    raw_lines = []
                    for line in raw_text.splitlines():
                        line = self.normalize_text(line.strip())
                        if not line:
                            continue
                        if re.fullmatch(r"\d{1,2}:\d{2}", line):
                            continue
                        if line.lower() in {"encaminhada", "forwarded"}:
                            continue
                        raw_lines.append(line)
                    if raw_lines:
                        return "\n".join(raw_lines).strip()
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
                if not combined:
                    continue

                visible_time = self.extract_visible_time_from_container(container)

                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contact': contact_name,
                    'phone_number': phone_number or "",
                    'last_message': combined,
                    'message': combined,
                    'visible_time': visible_time,
                    'status': 'new'
                }
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

    def process_active_open_chat_messages(self):
        """Detect new incoming messages in the chat that is already open, even without unread badge."""
        try:
            contact_name = self.extract_open_chat_contact_name()
            if not contact_name:
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
        self.driver.get("https://web.whatsapp.com")
        wait = WebDriverWait(self.driver, 60)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))
            logging.info("WhatsApp Web session is already authenticated")
            return
        except TimeoutException:
            logging.info("WhatsApp Web is not authenticated yet")

        input("Escaneie o QR code e pressione Enter...")
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
            encoded_message = quote(normalized_message)

            self.driver.get(f"https://web.whatsapp.com/send?phone={normalized_phone}&text={encoded_message}")

            wait = WebDriverWait(self.driver, 40)
            send_box = wait.until(EC.element_to_be_clickable((
                By.XPATH,
                "//footer//div[@contenteditable='true']"
            )))
            time.sleep(1.2)

            current_box_text = self.normalize_text(send_box.text or "")
            if not current_box_text:
                send_box.click()
                send_box.send_keys(normalized_message)

            sent = False
            for attempt in range(3):
                # O envio usa retry porque o WhatsApp Web às vezes digita o texto, mas demora para confirmar o clique.
                logging.info(f"Send attempt {attempt + 1} for {phone_number}")
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
            self.append_sent_message_history(history_entry)
            logging.info(f"Message sent to {phone_number}")
            return history_entry
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

            for item in message_batch:
                item['unread_count'] = conversation_info['unread_count']

            logging.info(f"Latest message from {conversation_info['contact']}: {last_text}")
            logging.info(f"Detected phone number: {phone_number or 'not found'}")
            return message_batch
        except Exception as e:
            logging.error(f"Error getting message from {conversation_info.get('contact', 'unknown')}: {e}")
            return None
    
    def process_unopened_messages(self):
        """Process only one unread conversation."""
        try:
            self.load_data()
            
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

    def process_all_unopened_messages(self, verbose=True):
        """Process every unread conversation and collect all newly received messages."""
        try:
            self.load_data()

            wait = WebDriverWait(self.driver, 60)
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']")))

            conversations = self.find_all_unopened_conversations(verbose=verbose)
            if not conversations:
                if verbose:
                    logging.info("No unread conversations to process")
                return []

            new_messages = []
            for conversation in conversations:
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
                        unread_count = len(self.driver.find_elements(
                            By.XPATH,
                            "//div[@data-testid='cell-frame-container'][.//span[@data-testid='icon-unread-count'] or .//span[contains(@aria-label, 'unread')]]",
                        ))
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
            self.driver.quit()
            logging.info("Chrome driver closed")

    def process_last_conversation_message(self):
        """Process the last visible conversation from the sidebar."""
        try:
            self.load_data()

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
    default_test_number = "+5511926019825"
    default_test_message = "Olá! Esta é uma mensagem de teste enviada pelo WhatsApp Web."

    mode = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if not mode:
        chosen = input("Digite '1' para ler conversa não aberta, '2' para enviar mensagem de teste, '3' para pegar a última conversa ou '4' para monitorar tudo: ").strip()
        if chosen == "2":
            mode = "send"
        elif chosen == "3":
            mode = "last"
        elif chosen == "4":
            mode = "monitor_all"
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
    else:
        whatsapp.monitor_new_conversations("last" if mode == "last" else "unopened")
        whatsapp.driver.quit()
        logging.info("Chrome driver closed")
