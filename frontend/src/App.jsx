// frontend/src/App.js
import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [file, setFile] = useState(null);
  const [format, setFormat] = useState('mp4');
  const [resolution, setResolution] = useState('720p');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('info'); // info, success, error, warning
  const [darkMode, setDarkMode] = useState(() => {
    // Initialize from localStorage or system preference
    const savedMode = localStorage.getItem('darkMode');
    if (savedMode !== null) {
      return savedMode === 'true';
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  // Apply dark mode class to body when darkMode state changes
  useEffect(() => {
    document.body.classList.toggle('dark-mode', darkMode);
    localStorage.setItem('darkMode', darkMode);
  }, [darkMode]);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const toggleDarkMode = () => {
    setDarkMode(prevMode => !prevMode);
  };

  const fetchJobs = async () => {
    try {
      const response = await fetch('http://localhost:8000/jobs');
      const data = await response.json();
      setJobs(data);
    } catch (error) {
      console.error('Error fetching jobs:', error);
      showMessage('Unable to fetch jobs. Please try again later.', 'error');
    }
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
      showMessage(`Selected file: ${selectedFile.name}`, 'info');
    }
  };

  const showMessage = (text, type = 'info') => {
    setMessage(text);
    setMessageType(type);
  };

  // Mock progress updates (in a real app, you'd use XMLHttpRequest or fetch with a progress event)
  const simulateProgress = () => {
    let progress = 0;
    const interval = setInterval(() => {
      progress += Math.random() * 10;
      if (progress > 100) progress = 100;
      setUploadProgress(Math.floor(progress));
      if (progress === 100) clearInterval(interval);
    }, 300);
    return interval;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!file) {
      showMessage('Please select a file', 'error');
      return;
    }

    setUploading(true);
    showMessage('Uploading video...', 'info');
    setUploadProgress(0);
    
    // Start progress simulation
    const progressInterval = simulateProgress();

    const formData = new FormData();
    formData.append('file', file);
    formData.append('format', format);
    formData.append('resolution', resolution);

    try {
      const response = await fetch('http://localhost:8000/upload', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();
      
      // Clear progress simulation
      clearInterval(progressInterval);
      setUploadProgress(100);
      
      if (response.ok) {
        showMessage('Video uploaded successfully! Job queued for processing.', 'success');
        setFile(null);
        fetchJobs();
      } else {
        showMessage(`Error: ${result.detail}`, 'error');
      }
    } catch (error) {
      clearInterval(progressInterval);
      showMessage(`Error: ${error.message}`, 'error');
    } finally {
      setUploading(false);
    }
  };

  // Helper function to render appropriate status badge
  const renderStatusBadge = (status) => {
    const statusClasses = {
      completed: 'status-completed',
      pending: 'status-pending',
      processing: 'status-processing',
      failed: 'status-failed',
    };
    
    const statusIcons = {
      completed: '✓',
      pending: '⏳',
      processing: '⚙️',
      failed: '✕',
    };
    
    return (
      <span className={`status-badge ${statusClasses[status] || 'status-pending'}`}>
        <span>{statusIcons[status] || '⏳'}</span>
        {status}
      </span>
    );
  };

  return (
    <div className={`App ${darkMode ? 'dark-mode' : 'light-mode'}`}>
      <header className="App-header">
        <h1>Video Transcoding Service</h1>
        <button 
          className="theme-toggle" 
          onClick={toggleDarkMode} 
          aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
          title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
        >
          {darkMode ? '☀️' : '🌙'}
        </button>
      </header>
      <main>
        <section className="upload-section">
          <h2>Upload Video</h2>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="file">Select Video File</label>
              <div className="file-input-container">
                <input 
                  type="file" 
                  id="file" 
                  accept="video/*" 
                  onChange={handleFileChange}
                  disabled={uploading}
                />
                <div className="file-input-content">
                  <div className="file-icon">
                    {file ? '📁' : '📷'}
                  </div>
                  {file ? (
                    <div className="file-name">{file.name}</div>
                  ) : (
                    <div className="file-info">
                      Drag and drop your video here<br />
                      or click to browse
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            <div className="form-group">
              <label htmlFor="format">Output Format</label>
              <select 
                id="format" 
                value={format} 
                onChange={(e) => setFormat(e.target.value)}
                disabled={uploading}
              >
                <option value="mp4">MP4</option>
                <option value="webm">WebM</option>
                <option value="mkv">MKV</option>
                <option value="avi">AVI</option>
                <option value="mov">MOV</option>
                <option value="gif">GIF</option>
              </select>
            </div>
            
            <div className="form-group">
              <label htmlFor="resolution">Output Resolution</label>
              <select 
                id="resolution" 
                value={resolution} 
                onChange={(e) => setResolution(e.target.value)}
                disabled={uploading}
              >
                <option value="360p">360p</option>
                <option value="480p">480p</option>
                <option value="720p">720p (HD)</option>
                <option value="1080p">1080p (Full HD)</option>
                <option value="2160p">2160p (4K)</option>
              </select>
            </div>
            
            <button 
              type="submit" 
              disabled={uploading || !file}
              className={uploading ? 'loading' : ''}
            >
              {uploading ? 'Uploading...' : 'Upload and Process'}
            </button>
            
            {uploading && (
              <div className="progress-container">
                <div className="progress-bar" style={{ width: `${uploadProgress}%` }}></div>
              </div>
            )}
          </form>
          
          {message && (
            <div className={`message message-${messageType}`}>
              <div className="message-icon">
                {messageType === 'success' && '✓'}
                {messageType === 'error' && '✕'}
                {messageType === 'warning' && '⚠️'}
                {messageType === 'info' && 'ℹ️'}
              </div>
              <div>{message}</div>
            </div>
          )}
        </section>
        
        <section className="jobs-section">
          <h2>Processing Jobs</h2>
          {jobs.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📋</div>
              <p>No active jobs</p>
              <p>Upload a video to get started</p>
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Filename</th>
                    <th>Format</th>
                    <th>Resolution</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.job_id}>
                      <td>{job.job_id}</td>
                      <td title={job.filename}>
                        {job.filename.length > 20 
                          ? job.filename.substring(0, 20) + '...' 
                          : job.filename}
                      </td>
                      <td>{job.format}</td>
                      <td>{job.resolution}</td>
                      <td>{renderStatusBadge(job.status)}</td>
                      <td>
                        {job.status === 'completed' ? (
                          <a 
                            href={`http://localhost:8000/download/${job.job_id}`}
                            className="download-button"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            ⬇️ Download
                          </a>
                        ) : (
                          <span className="text-light">-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;