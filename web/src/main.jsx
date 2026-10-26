import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/vazirmatn/400.css';
import '@fontsource/vazirmatn/500.css';
import '@fontsource/vazirmatn/600.css';
import '@fontsource/vazirmatn/700.css';
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import Portal from './Portal.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(<React.StrictMode>{location.pathname.replace(/\/$/,'')==='/portal'?<Portal/>:<App/>}</React.StrictMode>);
