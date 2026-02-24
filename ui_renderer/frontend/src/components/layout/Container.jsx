import React from 'react';
import './Container.css';

export const Container = ({ children, style, className = '' }) => {
  return (
    <div className={`container ${className}`} style={style}>
      {children}
    </div>
  );
};
