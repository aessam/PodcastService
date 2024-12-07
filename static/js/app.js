// React components
const { useState, useEffect } = React;

// Error Boundary Component
class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, errorMessage: '' };
    }

    static getDerivedStateFromError(error) {
        return { 
            hasError: true, 
            errorMessage: error && error.message ? error.message : 'Unknown error'
        };
    }

    componentDidCatch(error, errorInfo) {
        console.error('React error:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="flex flex-col items-center justify-center min-h-screen p-4">
                    <div className="text-xl text-red-600 mb-4">Something went wrong</div>
                    <div className="text-gray-600">{this.state.errorMessage}</div>
                    <button 
                        onClick={() => window.location.reload()} 
                        className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
                    >
                        Reload Page
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

function App() {
    const [user, setUser] = useState(null);
    const [view, setView] = useState('dashboard');
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    
    useEffect(() => {
        // Check if user is already logged in
        const checkAuth = async () => {
            try {
                const response = await fetch('/api/user/settings');
                if (response.ok) {
                    const settings = await response.json();
                    setUser({ settings });
                }
            } catch (error) {
                console.error('Auth check failed:', error);
                setError('Failed to check authentication status');
            } finally {
                setLoading(false);
            }
        };
        
        checkAuth();
    }, []);
    
    const handleLogin = (userData) => {
        setUser(userData);
        setView('dashboard');
        setError(null);
    };
    
    const handleLogout = async () => {
        try {
            await fetch('/api/logout', { method: 'POST' });
            setUser(null);
            setView('login');
            setError(null);
        } catch (error) {
            console.error('Logout failed:', error);
            setError('Failed to logout');
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-xl text-gray-600 loading">Loading...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-xl text-red-600">{error}</div>
            </div>
        );
    }
    
    if (!user) {
        return (
            <ErrorBoundary>
                <Auth onLogin={handleLogin} />
            </ErrorBoundary>
        );
    }
    
    return (
        <ErrorBoundary>
            <div className="min-h-screen">
                <nav className="bg-indigo-600 text-white shadow-lg">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="flex justify-between h-16">
                            <div className="flex items-center">
                                <span className="text-xl font-bold">Podcast Service</span>
                            </div>
                            <div className="flex items-center space-x-4">
                                <button
                                    onClick={() => setView('dashboard')}
                                    className={`px-3 py-2 rounded-md ${view === 'dashboard' ? 'bg-indigo-700' : 'hover:bg-indigo-700'}`}
                                >
                                    Dashboard
                                </button>
                                <button
                                    onClick={handleLogout}
                                    className="px-3 py-2 rounded-md hover:bg-indigo-700"
                                >
                                    Logout
                                </button>
                            </div>
                        </div>
                    </div>
                </nav>
                
                <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                    {view === 'dashboard' && <Dashboard />}
                </main>
            </div>
        </ErrorBoundary>
    );
}

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', () => {
    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(
        <ErrorBoundary>
            <App />
        </ErrorBoundary>
    );
}); 