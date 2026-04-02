import "@testing-library/jest-dom";

// jsdom doesn't implement scrollIntoView; stub it globally
Element.prototype.scrollIntoView = () => {};
