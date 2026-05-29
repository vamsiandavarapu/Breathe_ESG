import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import './App.css';
import Dashboard from './pages/Dashboard';
import ReviewPage from './pages/ReviewPage';
import UploadPage from './pages/UploadPage';
import API_BASE_URL from './apiConfig';

const LoginPage = ({ onLogin, setToken, setTenant, setUser }) => {
  const [username, setUsername] = useState('analyst');
  const [password, setPassword] = useState('demo1234');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const response = await axios.post(`${API_BASE_URL}/auth/login/`, {
        username,
        password,
      });
      
      const { token, user, tenants } = response.data;
      setToken(token);
      setUser(user);
      
      if (tenants && tenants.length > 0) {
        setTenant(tenants[0]);
      }
      
      onLogin(true);
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.error || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-box">
        <h1>🌿 Breathe ESG</h1>
        <p>Carbon Data Ingestion Platform</p>
        <form onSubmit={handleLogin}>
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          />
          {error && <p className="error-message">{error}</p>}
          <button type="submit" disabled={loading}>
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
        <div className="demo-info">
          <p><strong>Demo Credentials:</strong></p>
          <p>👤 analyst / demo1234</p>
          <p>👤 admin / admin1234</p>
        </div>
      </div>
    </div>
  );
};

const Navigation = ({ user, tenant, onLogout }) => {
  const location = useLocation();
  
  return (
    <nav className="navbar">
      <div className="nav-brand">
        <span>🌿 Breathe ESG</span>
      </div>
      <div className="nav-links">
        <a href="/dashboard" style={{ color: location.pathname === '/dashboard' ? '#667eea' : '#333' }}>Dashboard</a>
        <a href="/review" style={{ color: location.pathname === '/review' ? '#667eea' : '#333' }}>Review</a>
        <a href="/upload" style={{ color: location.pathname === '/upload' ? '#667eea' : '#333' }}>Upload</a>
      </div>
      <div className="nav-user">
        <span>{user?.username} @ {tenant?.name}</span>
        <button onClick={onLogout} className="logout-btn">Logout</button>
      </div>
    </nav>
  );
};

const ProtectedLayout = ({ user, tenant, token, onLogout, children }) => {
  return (
    <div className="app-container">
      <Navigation user={user} tenant={tenant} onLogout={onLogout} />
      <main className="main-content">
        {children}
      </main>
    </div>
  );
};

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [tenant, setTenant] = useState(null);

  useEffect(() => {
    const savedToken = localStorage.getItem('authToken');
    const savedUser = localStorage.getItem('authUser');
    const savedTenant = localStorage.getItem('authTenant');
    
    if (savedToken && savedUser && savedTenant) {
      setToken(savedToken);
      setUser(JSON.parse(savedUser));
      setTenant(JSON.parse(savedTenant));
      setIsLoggedIn(true);
    }
  }, []);

  useEffect(() => {
    if (token && user && tenant) {
      localStorage.setItem('authToken', token);
      localStorage.setItem('authUser', JSON.stringify(user));
      localStorage.setItem('authTenant', JSON.stringify(tenant));
    }
  }, [token, user, tenant]);

  const handleLogout = () => {
    setIsLoggedIn(false);
    setToken(null);
    setUser(null);
    setTenant(null);
    localStorage.removeItem('authToken');
    localStorage.removeItem('authUser');
    localStorage.removeItem('authTenant');
  };

  return (
    <Router>
      <Routes>
        <Route path="/login" element={
          isLoggedIn ? <ProtectedLayout user={user} tenant={tenant} token={token} onLogout={handleLogout}><Dashboard token={token} tenant={tenant} /></ProtectedLayout> : 
          <LoginPage onLogin={setIsLoggedIn} setToken={setToken} setTenant={setTenant} setUser={setUser} />
        } />
        <Route path="/" element={
          isLoggedIn ? <ProtectedLayout user={user} tenant={tenant} token={token} onLogout={handleLogout}><Dashboard token={token} tenant={tenant} /></ProtectedLayout> : 
          <LoginPage onLogin={setIsLoggedIn} setToken={setToken} setTenant={setTenant} setUser={setUser} />
        } />
        <Route path="/dashboard" element={
          isLoggedIn ? <ProtectedLayout user={user} tenant={tenant} token={token} onLogout={handleLogout}><Dashboard token={token} tenant={tenant} /></ProtectedLayout> : 
          <LoginPage onLogin={setIsLoggedIn} setToken={setToken} setTenant={setTenant} setUser={setUser} />
        } />
        <Route path="/review" element={
          isLoggedIn ? <ProtectedLayout user={user} tenant={tenant} token={token} onLogout={handleLogout}><ReviewPage token={token} tenant={tenant} /></ProtectedLayout> : 
          <LoginPage onLogin={setIsLoggedIn} setToken={setToken} setTenant={setTenant} setUser={setUser} />
        } />
        <Route path="/upload" element={
          isLoggedIn ? <ProtectedLayout user={user} tenant={tenant} token={token} onLogout={handleLogout}><UploadPage token={token} tenant={tenant} /></ProtectedLayout> : 
          <LoginPage onLogin={setIsLoggedIn} setToken={setToken} setTenant={setTenant} setUser={setUser} />
        } />
      </Routes>
    </Router>
  );
}

export default App;
