import React from 'react';
import './Text.css';

export const Text = ({ children, variant = 'body', className = '' }) => {
  return <p className={`text text--${variant} ${className}`}>{children}</p>;
};
