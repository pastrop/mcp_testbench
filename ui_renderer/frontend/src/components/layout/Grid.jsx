import React from 'react';
import './Grid.css';

export const Grid = ({ children, columns = 2, gap = 'md', className = '' }) => {
  const style = {
    gridTemplateColumns: `repeat(${columns}, 1fr)`,
    gap: `var(--spacing-${gap})`,
  };

  return (
    <div className={`grid ${className}`} style={style}>
      {children}
    </div>
  );
};
