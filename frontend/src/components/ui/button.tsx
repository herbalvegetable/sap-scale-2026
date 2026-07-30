import type { ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "ui-button",
  {
    variants: {
      variant: {
        primary: "ui-button--primary",
        outline: "ui-button--outline",
        ghost: "ui-button--ghost",
      },
      size: {
        default: "ui-button--default",
        small: "ui-button--small",
      },
    },
    defaultVariants: { variant: "primary", size: "default" },
  },
);

type Props = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, ...props }: Props) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
