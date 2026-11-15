"use client";

import { useActionState } from "react";
import { login, type LoginState } from "./actions";

export function LoginForm() {
  const [state, formAction, pending] = useActionState<LoginState, FormData>(
    login,
    {},
  );

  return (
    <form action={formAction}>
      <p>
        <label htmlFor="email">Email</label>
        <br />
        <input id="email" name="email" type="email" autoComplete="email" required />
      </p>
      <p>
        <label htmlFor="password">Password</label>
        <br />
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
      </p>
      {state.error && <p role="alert">{state.error}</p>}
      <button type="submit" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
