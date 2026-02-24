import React from 'react';
import './Label.css';

export const Label = ({ children, className = '' }) => {
  return <span className={`label ${className}`}>{children}</span>;
};
