import React from 'react';
import './Section.css';

export const Section = ({ children, title, description, className = '' }) => {
  return (
    <section className={`section ${className}`}>
      {title && <h2 className="section__title">{title}</h2>}
      {description && <p className="section__description">{description}</p>}
      <div className="section__content">{children}</div>
    </section>
  );
};
