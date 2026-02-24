import React, { useState } from 'react';
import './Tabs.css';

export const Tabs = ({ tabs = [], defaultTab = 0, className = '' }) => {
  const [activeTab, setActiveTab] = useState(defaultTab);

  if (!tabs || tabs.length === 0) {
    return null;
  }

  return (
    <div className={`tabs ${className}`}>
      <div className="tabs__header">
        {tabs.map((tab, index) => (
          <button
            key={index}
            className={`tabs__button ${activeTab === index ? 'tabs__button--active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="tabs__content">
        {tabs[activeTab] && tabs[activeTab].content}
      </div>
    </div>
  );
};
