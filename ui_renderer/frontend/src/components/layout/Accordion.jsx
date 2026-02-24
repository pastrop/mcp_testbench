import React, { useState } from 'react';
import './Accordion.css';

export const Accordion = ({ items = [], allowMultiple = false, className = '' }) => {
  const [openIndexes, setOpenIndexes] = useState([]);

  const toggleItem = (index) => {
    if (allowMultiple) {
      setOpenIndexes((prev) =>
        prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]
      );
    } else {
      setOpenIndexes((prev) => (prev.includes(index) ? [] : [index]));
    }
  };

  if (!items || items.length === 0) {
    return null;
  }

  return (
    <div className={`accordion ${className}`}>
      {items.map((item, index) => (
        <div key={index} className="accordion__item">
          <button
            className="accordion__header"
            onClick={() => toggleItem(index)}
          >
            <span className="accordion__title">{item.title}</span>
            <span className={`accordion__icon ${openIndexes.includes(index) ? 'accordion__icon--open' : ''}`}>
              ▼
            </span>
          </button>
          {openIndexes.includes(index) && (
            <div className="accordion__content">{item.content}</div>
          )}
        </div>
      ))}
    </div>
  );
};
