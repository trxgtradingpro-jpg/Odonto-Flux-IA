declare module "@odontoflux/ui" {
  import * as React from "react";

  export function cn(...inputs: Array<string | false | null | undefined>): string;

  export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "default" | "outline" | "destructive" | "ghost";
  }
  export const Button: React.ForwardRefExoticComponent<
    ButtonProps & React.RefAttributes<HTMLButtonElement>
  >;

  export function Card(props: React.HTMLAttributes<HTMLDivElement>): JSX.Element;
  export function CardHeader(props: React.HTMLAttributes<HTMLDivElement>): JSX.Element;
  export function CardTitle(props: React.HTMLAttributes<HTMLHeadingElement>): JSX.Element;
  export function CardDescription(props: React.HTMLAttributes<HTMLParagraphElement>): JSX.Element;
  export function CardContent(props: React.HTMLAttributes<HTMLDivElement>): JSX.Element;

  export function Input(props: React.InputHTMLAttributes<HTMLInputElement>): JSX.Element;

  export function Badge(props: React.HTMLAttributes<HTMLDivElement>): JSX.Element;

  export function Table(props: React.TableHTMLAttributes<HTMLTableElement>): JSX.Element;
  export function THead(props: React.HTMLAttributes<HTMLTableSectionElement>): JSX.Element;
  export function TBody(props: React.HTMLAttributes<HTMLTableSectionElement>): JSX.Element;
  export function TR(props: React.HTMLAttributes<HTMLTableRowElement>): JSX.Element;
  export function TH(props: React.ThHTMLAttributes<HTMLTableCellElement>): JSX.Element;
  export function TD(props: React.TdHTMLAttributes<HTMLTableCellElement>): JSX.Element;
}
