const API_BASE_URL = process.env.REACT_APP_API_URL || (process.env.NODE_ENV === 'development' ? 'http://localhost:8000/api' : '');

if (!API_BASE_URL) {
  throw new Error('REACT_APP_API_URL is not set. Please configure it in Vercel environment variables and rebuild the frontend.');
}

export default API_BASE_URL;
