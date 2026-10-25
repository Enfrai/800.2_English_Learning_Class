/* Provide labelled native controls styled by the shared Ako UI kit.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import { useId, type InputHTMLAttributes, type ButtonHTMLAttributes } from "react";

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "autoComplete"> & {
  label: string;
  autocomplete?: string;
};

export function TextField({ label, autocomplete, id, ...props }: TextFieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return <div className="field">
    <label htmlFor={inputId} className={props.required ? "req" : undefined}>{label}</label>
    <input {...props} id={inputId} type={props.type ?? "text"} autoComplete={autocomplete} />
  </div>;
}

export function Button({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className={`btn ${className}`.trim()} />;
}
