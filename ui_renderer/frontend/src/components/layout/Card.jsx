import React from 'react';
import './Card.css';

export const Card = ({
  children,
  title,
  subtitle,
  variant = 'default',
  className = '',
}) => {
  return (
    <div className={`card card--${variant} ${className}`}>
      {(title || subtitle) && (
        <div className="card__header">
          {title && <h3 className="card__title">{title}</h3>}
          {subtitle && <p className="card__subtitle">{subtitle}</p>}
        </div>
      )}
      <div className="card__content">{children}</div>
    </div>
  );
};
