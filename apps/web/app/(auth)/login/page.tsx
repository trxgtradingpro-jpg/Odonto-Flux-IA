"use client";

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from '@odontoflux/ui';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';

import { setAccessToken } from '@/lib/auth';
import { api } from '@/lib/api';

const loginSchema = z.object({
  email: z.string().email('Informe um e-mail válido'),
  password: z.string().min(8, 'A senha precisa ter pelo menos 8 caracteres'),
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const form = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: 'owner@sorrisosul.com',
      password: 'Odonto@123',
    },
  });

  const loginMutation = useMutation({
    mutationFn: async (values: LoginForm) => {
      const response = await api.post('/auth/login', values);
      return response.data;
    },
    onSuccess: (data) => {
      setAccessToken(data.access_token);
      toast.success('Acesso realizado com sucesso.');
      router.push('/dashboard');
    },
    onError: () => {
      toast.error('Falha no login. Verifique e-mail e senha.');
    },
  });

  return (
    <Card>
      <CardHeader>
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">OdontoFlux</p>
        <CardTitle className="text-2xl">Entrar na plataforma</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit((values) => {
            loginMutation.mutate(values);
          })}
        >
          <div className="space-y-1">
            <label className="text-sm font-medium">E-mail</label>
            <Input type="email" placeholder="voce@clinica.com" {...form.register('email')} />
            {form.formState.errors.email ? (
              <p className="text-xs text-red-600">{form.formState.errors.email.message}</p>
            ) : null}
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium">Senha</label>
            <Input type="password" placeholder="********" {...form.register('password')} />
            {form.formState.errors.password ? (
              <p className="text-xs text-red-600">{form.formState.errors.password.message}</p>
            ) : null}
          </div>

          <Button className="w-full" type="submit" disabled={loginMutation.isPending}>
            {loginMutation.isPending ? 'Entrando...' : 'Entrar'}
          </Button>
        </form>

        <div className="mt-4 rounded-md bg-stone-100 p-3 text-xs text-stone-700">
          Use credenciais demo: <strong>owner@sorrisosul.com</strong> / <strong>Odonto@123</strong>
        </div>
      </CardContent>
    </Card>
  );
}
