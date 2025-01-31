import * as React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className = "", ...props }, ref) => (
    <div
      ref={ref}
      className={`rounded-lg border bg-card text-card-foreground shadow-sm ${className}`}
      {...props}
    />
  ),
);
Card.displayName = "Card";

export interface CardContentProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

const CardContent = React.forwardRef<HTMLDivElement, CardContentProps>(
  ({ className = "", ...props }, ref) => (
    <div ref={ref} className={`p-6 pt-0 ${className}`} {...props} />
  ),
);
CardContent.displayName = "CardContent";

export { Card, CardContent };
