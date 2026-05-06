import { Routes, Route } from 'react-router-dom';
import HomePage from './components/HomePage';
import SharedTripPage from './components/SharedTripPage';
import './App.css';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/share/:slug" element={<SharedTripPage />} />
    </Routes>
  );
}
