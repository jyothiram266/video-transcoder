// frontend/src/App.js
import React, { useState, useEffect, useRef } from 'react';
import './App.css';

function App() {
  const [file, setFile] = useState(null);
  const [videoPreview, setVideoPreview] = useState(null);
  const [format, setFormat] = useState('mp4');
  const [resolution, setResolution] = useState('720p');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('info');
  const [isDragging, setIsDragging] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [advancedSettings, setAdvancedSettings] = useState({
    frameRate: '30',
    audioCodec: 'aac',
    videoBitrate: 'medium',
    aspectRatio: 'original'
  });
  const [darkMode, setDarkMode] = useState(() => {
    const savedMode = localStorage.getItem('darkMode');
    if (savedMode !== null) {
      return savedMode === 'true';
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  
  const fileInputRef = useRef(null);
  const dropAreaRef = useRef(null);

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

  // Set up drag and drop event listeners
  useEffect(() => {
    const dropArea = dropAreaRef.current;
    if (!dropArea) return;

    const preventDefaults = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };

    const highlight = () => setIsDragging(true);
    const unhighlight = () => setIsDragging(false);

    const handleDrop = (e) => {
      preventDefaults(e);
      unhighlight();
      
      const dt = e.dataTransfer;
      const files = dt.files;
      
      if (files && files.length) {
        handleFiles(files);
      }
    };

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
      dropArea.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
      dropArea.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropArea.addEventListener(eventName, unhighlight, false);
    });

    dropArea.addEventListener('drop', handleDrop, false);

    return () => {
      ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.removeEventListener(eventName, preventDefaults, false);
      });
      
      ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.removeEventListener(eventName, highlight, false);
      });
      
      ['dragleave', 'drop'].forEach(eventName => {
        dropArea.removeEventListener(eventName, unhighlight, false);
      });
      
      dropArea.removeEventListener('drop', handleDrop, false);
    };
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

  const handleFiles = (fileList) => {
    const selectedFile = fileList[0];
    if (selectedFile && selectedFile.type.startsWith('video/')) {
      setFile(selectedFile);
      
      // Create a video preview
      const videoUrl = URL.createObjectURL(selectedFile);
      setVideoPreview(videoUrl);
      
      showMessage(`Selected file: ${selectedFile.name}`, 'info');
    } else {
      showMessage('Please select a valid video file', 'error');
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
    }
  };

  const showMessage = (text, type = 'info') => {
    setMessage(text);
    setMessageType(type);
    
    // Auto-hide success messages after 5 seconds
    if (type === 'success') {
      setTimeout(() => {
        setMessage('');
      }, 5000);
    }
  };

  // Simulated realistic progress updates
  const simulateProgress = () => {
    let progress = 0;
    let acceleration = 1.05;
    let deceleration = 0.8;
    
    // Random initial delay to simulate server processing
    setTimeout(() => {
      const interval = setInterval(() => {
        if (progress < 30) {
          // Start slow
          progress += (Math.random() * 2) * acceleration;
        } else if (progress < 70) {
          // Middle part - steady progress
          progress += (Math.random() * 3) * acceleration;
        } else if (progress < 90) {
          // Slow down as we approach end
          progress += (Math.random() * 1.5) * deceleration;
        } else if (progress < 99) {
          // Very slow at the end
          progress += (Math.random() * 0.5) * deceleration;
        }
        
        if (progress > 100) progress = 99; // Leave the last percent for completion
        
        setUploadProgress(Math.floor(progress));
        if (progress >= 99) clearInterval(interval);
      }, 200);
      
      return interval;
    }, Math.random() * 500 + 200);
  };

  const handleSettingsToggle = () => {
    setShowSettings(prev => !prev);
  };

  const handleAdvancedSettingChange = (setting, value) => {
    setAdvancedSettings(prev => ({
      ...prev,
      [setting]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!file) {
      showMessage('Please select a file', 'error');
      return;
    }

    setUploading(true);
    showMessage('Uploading and preparing video...', 'info');
    setUploadProgress(0);
    
    // Start progress simulation
    const progressInterval = simulateProgress();

    const formData = new FormData();
    formData.append('file', file);
    formData.append('format', format);
    formData.append('resolution', resolution);
    
    // Add advanced settings to form data
    Object.entries(advancedSettings).forEach(([key, value]) => {
      formData.append(key, value);
    });

    try {
      const response = await fetch('http://localhost:8000/upload', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();
      
      // Force complete the progress bar
      setUploadProgress(100);
      
      if (response.ok) {
        showMessage('Video uploaded successfully! Job queued for processing.', 'success');
        setFile(null);
        setVideoPreview(null);
        fetchJobs();
      } else {
        showMessage(`Error: ${result.detail}`, 'error');
      }
    } catch (error) {
      showMessage(`Error: ${error.message}`, 'error');
    } finally {
      setUploading(false);
    }
  };

  const getJobDuration = (job) => {
    // Simulated duration data - in real app you'd get this from the API
    return Math.floor(Math.random() * 300 + 30); // 30-330 seconds
  };

  // Helper function to render appropriate status badge with animation
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
        <span className={status === 'processing' ? 'spinning-icon' : ''}>{statusIcons[status] || '⏳'}</span>
        {status}
      </span>
    );
  };

  // Render job processing timeline
  const renderJobTimeline = (job) => {
    const stages = ['queued', 'analyzing', 'processing', 'finalizing', 'completed'];
    let currentStageIndex = 0;
    
    if (job.status === 'completed') {
      currentStageIndex = 4;
    } else if (job.status === 'processing') {
      currentStageIndex = Math.floor(Math.random() * 3) + 1; // Random stage 1-3
    } else if (job.status === 'failed') {
      currentStageIndex = -1; // Failed can happen at any stage
    }
    
    return (
      <div className="job-timeline">
        {stages.map((stage, index) => (
          <div 
            key={stage}
            className={`timeline-point ${index <= currentStageIndex ? 'completed' : ''} ${index === currentStageIndex && job.status === 'processing' ? 'current' : ''}`}
            title={stage.charAt(0).toUpperCase() + stage.slice(1)}
          >
            <div className="timeline-label">{stage.charAt(0).toUpperCase() + stage.slice(1)}</div>
          </div>
        ))}
        <div className="timeline-bar">
          <div 
            className="timeline-progress" 
            style={{ width: `${(currentStageIndex / (stages.length - 1)) * 100}%` }}
          ></div>
        </div>
      </div>
    );
  };

  return (
    <div className={`App ${darkMode ? 'dark-mode' : 'light-mode'}`}>
      <header className="App-header">
        <h1>
          <span className="logo-icon">🎬</span>
          Video Transcoding Service
          <span className="version-badge">v2.0</span>
        </h1>
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
              <div 
                ref={dropAreaRef}
                className={`file-input-container ${isDragging ? 'dragging' : ''} ${videoPreview ? 'has-video' : ''}`}
                onClick={() => fileInputRef.current && fileInputRef.current.click()}
              >
                <input 
                  ref={fileInputRef}
                  type="file" 
                  id="file" 
                  accept="video/*" 
                  onChange={handleFileChange}
                  disabled={uploading}
                />
                
                {videoPreview ? (
                  <div className="video-preview-container">
                    <video 
                      className="video-preview" 
                      src={videoPreview} 
                      controls
                      onClick={(e) => e.stopPropagation()}
                    />
                    <div className="file-info">
                      <div className="file-name">{file && file.name}</div>
                      <button 
                        type="button" 
                        className="clear-file-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setFile(null);
                          setVideoPreview(null);
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="file-input-content">
                    <div className={`file-icon ${isDragging ? 'pulse-animation' : ''}`}>
                      📷
                    </div>
                    <div className="file-info">
                      <div className="drop-text">Drop your video here</div>
                      <div className="or-divider">or</div>
                      <div className="browse-text">click to browse</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
            
            <div className="form-row">
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
                <label htmlFor="resolution">Resolution</label>
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
            </div>
            
            <div className="advanced-settings-toggle">
              <button 
                type="button" 
                className="toggle-settings-btn"
                onClick={handleSettingsToggle}
              >
                {showSettings ? 'Hide' : 'Show'} Advanced Settings
                <span className={`toggle-arrow ${showSettings ? 'open' : ''}`}>▼</span>
              </button>
            </div>
            
            {showSettings && (
              <div className="advanced-settings animated fadeIn">
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="frameRate">Frame Rate</label>
                    <select
                      id="frameRate"
                      value={advancedSettings.frameRate}
                      onChange={(e) => handleAdvancedSettingChange('frameRate', e.target.value)}
                      disabled={uploading}
                    >
                      <option value="24">24 fps (Film)</option>
                      <option value="25">25 fps (PAL)</option>
                      <option value="30">30 fps (Standard)</option>
                      <option value="60">60 fps (High)</option>
                    </select>
                  </div>
                  
                  <div className="form-group">
                    <label htmlFor="audioCodec">Audio Codec</label>
                    <select
                      id="audioCodec"
                      value={advancedSettings.audioCodec}
                      onChange={(e) => handleAdvancedSettingChange('audioCodec', e.target.value)}
                      disabled={uploading}
                    >
                      <option value="aac">AAC (Standard)</option>
                      <option value="mp3">MP3</option>
                      <option value="opus">Opus (High Quality)</option>
                    </select>
                  </div>
                </div>
                
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="videoBitrate">Video Quality</label>
                    <select
                      id="videoBitrate"
                      value={advancedSettings.videoBitrate}
                      onChange={(e) => handleAdvancedSettingChange('videoBitrate', e.target.value)}
                      disabled={uploading}
                    >
                      <option value="low">Low (Smaller file)</option>
                      <option value="medium">Medium (Balanced)</option>
                      <option value="high">High (Better quality)</option>
                    </select>
                  </div>
                  
                  <div className="form-group">
                    <label htmlFor="aspectRatio">Aspect Ratio</label>
                    <select
                      id="aspectRatio"
                      value={advancedSettings.aspectRatio}
                      onChange={(e) => handleAdvancedSettingChange('aspectRatio', e.target.value)}
                      disabled={uploading}
                    >
                      <option value="original">Original</option>
                      <option value="16:9">16:9 (Widescreen)</option>
                      <option value="4:3">4:3 (Standard)</option>
                      <option value="1:1">1:1 (Square)</option>
                      <option value="9:16">9:16 (Vertical)</option>
                    </select>
                  </div>
                </div>
              </div>
            )}
            
            <button 
              type="submit" 
              disabled={uploading || !file}
              className={uploading ? 'loading' : ''}
            >
              {uploading ? (
                <>
                  <span className="upload-spinner"></span>
                  Uploading...
                </>
              ) : (
                <>
                  <span className="upload-icon">⬆️</span>
                  Upload and Process
                </>
              )}
            </button>
            
            {uploading && (
              <div className="progress-container">
                <div className="progress-bar" style={{ width: `${uploadProgress}%` }}></div>
                <div className="progress-text">{uploadProgress}% Complete</div>
              </div>
            )}
          </form>
          
          {message && (
            <div className={`message message-${messageType} animated fadeIn`}>
              <div className="message-icon">
                {messageType === 'success' && '✓'}
                {messageType === 'error' && '✕'}
                {messageType === 'warning' && '⚠️'}
                {messageType === 'info' && 'ℹ️'}
              </div>
              <div>{message}</div>
              <button 
                className="close-message"
                onClick={() => setMessage('')}
                aria-label="Close message"
              >
                ✕
              </button>
            </div>
          )}
        </section>
        
        <section className="jobs-section">
          <h2>Processing Jobs</h2>
          {jobs.length === 0 ? (
            <div className="empty-state animated fadeIn">
              <div className="empty-icon">📋</div>
              <p>No active jobs</p>
              <p>Upload a video to get started</p>
              <button className="help-button" onClick={() => showMessage('Select a video file, choose your desired format and resolution, then click "Upload and Process"', 'info')}>
                Need help?
              </button>
            </div>
          ) : (
            <div className="table-container animated fadeIn">
              <table>
                <thead>
                  <tr>
                    <th>Filename</th>
                    <th>Format</th>
                    <th>Resolution</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.job_id} className="job-row">
                      <td title={job.filename}>
                        <div className="file-cell">
                          <span className="file-icon-small">🎬</span>
                          {job.filename.length > 20 
                            ? job.filename.substring(0, 20) + '...' 
                            : job.filename}
                        </div>
                      </td>
                      <td>{job.format}</td>
                      <td>{job.resolution}</td>
                      <td>{renderStatusBadge(job.status)}</td>
                      <td>
                        {job.status === 'processing' && renderJobTimeline(job)}
                        {job.status === 'pending' && <div className="pending-badge">In queue</div>}
                        {job.status === 'completed' && (
                          <div className="duration-info">
                            {getJobDuration(job)}s
                          </div>
                        )}
                        {job.status === 'failed' && <div className="error-text">Failed</div>}
                      </td>
                      <td>
                        {job.status === 'completed' ? (
                          <a 
                            href={`http://localhost:8000/download/${job.job_id}`}
                            className="download-button"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Download
                          </a>
                        ) : job.status === 'failed' ? (
                          <button className="retry-button">
                            Retry
                          </button>
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
      <footer className="app-footer">
        <p>© 2025 Video Transcoding Service</p>
        <div className="footer-links">
          <a href="#help">Help</a>
          <a href="#privacy">Privacy</a>
          <a href="#terms">Terms</a>
        </div>
      </footer>
    </div>
  );
}

export default App;