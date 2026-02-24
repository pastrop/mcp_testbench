import React from 'react';
import './Heading.css';

export const Heading = ({ level = 2, children, className = '' }) => {
  const Tag = `h${Math.min(Math.max(level, 1), 6)}`;

  return <Tag className={`heading heading--${level} ${className}`}>{children}</Tag>;
};
