function Dashboard() {
    const [url, setUrl] = React.useState('');
    const [title, setTitle] = React.useState('');
    const [processing, setProcessing] = React.useState(false);
    const [message, setMessage] = React.useState(null);
    
    const handleSubmit = async (e) => {
        e.preventDefault();
        setProcessing(true);
        setMessage(null);
        
        try {
            const response = await fetch('/api/process/episode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url, title: title || undefined })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Processing failed');
            }
            
            const result = await response.json();
            setMessage({
                type: 'success',
                text: 'Processing started successfully! Check history for updates.'
            });
            setUrl('');
            setTitle('');
        } catch (error) {
            setMessage({
                type: 'error',
                text: error.message
            });
        } finally {
            setProcessing(false);
        }
    };
    
    return (
        <div className="space-y-8">
            <div className="bg-white shadow sm:rounded-lg">
                <div className="px-4 py-5 sm:p-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">
                        Process New Episode
                    </h3>
                    <div className="mt-2 max-w-xl text-sm text-gray-500">
                        <p>Enter a podcast episode URL to start processing.</p>
                    </div>
                    <form onSubmit={handleSubmit} className="mt-5 space-y-4">
                        <div>
                            <label htmlFor="url" className="block text-sm font-medium text-gray-700">
                                Episode URL
                            </label>
                            <div className="mt-1">
                                <input
                                    type="url"
                                    name="url"
                                    id="url"
                                    required
                                    value={url}
                                    onChange={(e) => setUrl(e.target.value)}
                                    className="shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border-gray-300 rounded-md"
                                    placeholder="https://example.com/podcast-episode"
                                    disabled={processing}
                                />
                            </div>
                        </div>
                        
                        <div>
                            <label htmlFor="title" className="block text-sm font-medium text-gray-700">
                                Custom Title (Optional)
                            </label>
                            <div className="mt-1">
                                <input
                                    type="text"
                                    name="title"
                                    id="title"
                                    value={title}
                                    onChange={(e) => setTitle(e.target.value)}
                                    className="shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border-gray-300 rounded-md"
                                    placeholder="My Podcast Episode"
                                    disabled={processing}
                                />
                            </div>
                        </div>
                        
                        <div>
                            <button
                                type="submit"
                                disabled={processing}
                                className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
                                    processing
                                        ? 'bg-indigo-400 cursor-not-allowed'
                                        : 'bg-indigo-600 hover:bg-indigo-700'
                                }`}
                            >
                                {processing ? "Processing..." : "Process Episode"}
                            </button>
                        </div>
                    </form>
                    
                    {message && (
                        <div className={`mt-4 p-4 rounded-md ${
                            message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                        }`}>
                            {message.text}
                        </div>
                    )}
                </div>
            </div>
            
            <div className="bg-white shadow sm:rounded-lg">
                <div className="px-4 py-5 sm:p-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">
                        Processing Steps
                    </h3>
                    <div className="mt-4 space-y-4">
                        <div className="flex items-center space-x-4">
                            <div className="flex-shrink-0">
                                <span className="h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center">
                                    1
                                </span>
                            </div>
                            <div>
                                <p className="text-sm font-medium text-gray-900">Download</p>
                                <p className="text-sm text-gray-500">Downloads the podcast episode audio</p>
                            </div>
                        </div>
                        
                        <div className="flex items-center space-x-4">
                            <div className="flex-shrink-0">
                                <span className="h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center">
                                    2
                                </span>
                            </div>
                            <div>
                                <p className="text-sm font-medium text-gray-900">Transcribe</p>
                                <p className="text-sm text-gray-500">Transcribes the audio using MLX Whisper</p>
                            </div>
                        </div>
                        
                        <div className="flex items-center space-x-4">
                            <div className="flex-shrink-0">
                                <span className="h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center">
                                    3
                                </span>
                            </div>
                            <div>
                                <p className="text-sm font-medium text-gray-900">Summarize</p>
                                <p className="text-sm text-gray-500">Generates a summary using GPT-4</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
} 