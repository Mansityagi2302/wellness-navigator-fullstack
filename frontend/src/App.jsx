import { useState } from 'react'
import './App.css'

// This points to your FastAPI backend
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

function App() {
  // --- Form State ---
  const [userName, setUserName] = useState('')
  const [goal, setGoal] = useState('')
  const [activityLevel, setActivityLevel] = useState('')
  const [primaryMetric, setPrimaryMetric] = useState('')
  const [message, setMessage] = useState('')

  // --- AI & Logic State ---
  const [conversation, setConversation] = useState([])
  const [focusArea, setFocusArea] = useState(null)
  const [readyToSync, setReadyToSync] = useState(false)
  const [pendingQuestion, setPendingQuestion] = useState(null)
  const [recommended, setRecommended] = useState([])
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [safetyFlag, setSafetyFlag] = useState(null)

  // Helper to update the chat transcript
  const addMessage = (entry) => {
    setConversation((prev) => [...prev, entry])
  }

  // --- Logic: Talk to the AI Coach ---
  const handleCoach = async () => {
    setStatus(null)
    setSafetyFlag(null)
    
    if (!userName.trim()) {
      setStatus('Please add your name so we can personalize guidance.')
      return
    }
    if (!message.trim()) {
      setStatus('Please enter a message to talk to the coach.')
      return
    }

    setLoading(true)
    addMessage({ role: 'user', text: message })

    try {
      const res = await fetch(`${API_BASE}/coach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_name: userName,
          message,
          goal: goal || null,
          activity_level: activityLevel || null,
          primary_metric: primaryMetric || null,
          focus_area: focusArea || null,
        }),
      })

      if (!res.ok) throw new Error('Coach request failed')
      
      const data = await res.json()
      
      // Update the app state based on AI response
      setFocusArea(data.focus_area)
      setReadyToSync(data.ready_to_sync)
      setPendingQuestion(data.next_question || null)
      setRecommended(data.recommended_actions || [])
      setSafetyFlag(data.safety_flag || null)

      // Create the Coach's chat bubble text
      let coachText = `Focus area identified: ${data.focus_area}.`
      if (data.safety_flag) {
        coachText = data.safety_flag
      } else if (data.next_question) {
        coachText += ` ${data.next_question}`
      } else if (data.ready_to_sync) {
        coachText += ' All required fields captured. You can now sync this milestone!'
      }
      
      addMessage({ role: 'coach', text: coachText })
      setMessage('') // Clear the input box
    } catch (err) {
      setStatus('Something went wrong reaching the coach. Please check your backend.')
    } finally {
      setLoading(false)
    }
  }

  // --- Logic: Sync Data to Supabase ---
  const handleSync = async () => {
    if (!focusArea || !goal || !primaryMetric || !userName) {
      setStatus('Need name, goal, metric, and focus area before syncing.');
      return;
    }

    setStatus('Syncing to Supabase...');
    
    try {
      const res = await fetch(`${API_BASE}/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_name: userName,
          focus_area: focusArea,
          health_metric: primaryMetric,
          primary_goal: goal,
        }),
      });

      if (!res.ok) throw new Error('Sync failed');

      setStatus('✅ Milestone synced securely to your history!');
      setReadyToSync(false); // Disable button after success
    } catch (err) {
      console.error(err);
      setStatus('❌ Could not sync. Check your Supabase connection.');
    }
  };

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">Wellness Navigator AI</p>
          <h1>Stay on track with empathetic guidance</h1>
          <p className="subhead">Proactively monitor goals and get tailored recommendations.</p>
        </div>
        <div className="summary-card">
          <div className="summary-item"><span className="label">Focus:</span> <strong>{focusArea ?? 'Pending'}</strong></div>
          <div className="summary-item"><span className="label">Ready to Sync:</span> <strong>{readyToSync ? 'Yes' : 'No'}</strong></div>
        </div>
      </header>

      <main className="grid">
        {/* Left Panel: Profile */}
        <section className="panel">
          <h2>Profile & Metrics</h2>
          <div className="field">
            <label>Name</label>
            <input value={userName} onChange={(e) => setUserName(e.target.value)} placeholder="Alex" />
          </div>
          <div className="field">
            <label>Primary Goal</label>
            <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Run a 5k" />
          </div>
          <div className="field">
            <label>Activity Level</label>
            <input value={activityLevel} onChange={(e) => setActivityLevel(e.target.value)} placeholder="Active 3x/week" />
          </div>
          <div className="field">
            <label>Primary Metric</label>
            <input value={primaryMetric} onChange={(e) => setPrimaryMetric(e.target.value)} placeholder="Steps or Sleep hours" />
          </div>
          <button className="primary" onClick={handleCoach} disabled={loading}>
            {loading ? 'Processing...' : 'Send Check-in'}
          </button>
          {status && <p className="status">{status}</p>}
        </section>

        {/* Right Panel: Chat & Sync */}
        <section className="panel">
          <h2>Coach Interaction</h2>
          <textarea 
            rows={4} 
            value={message} 
            onChange={(e) => setMessage(e.target.value)} 
            placeholder="Talk to the coach about your progress..." 
          />
          <div className="actions">
            <button className="secondary" onClick={handleCoach}>Ask Coach</button>
            <button className="primary" onClick={handleSync} disabled={!readyToSync}>Sync Milestone</button>
          </div>

          <div className="transcript" style={{ marginTop: '20px' }}>
            {conversation.length === 0 && <p className="muted">Your conversation will appear here.</p>}
            {conversation.map((entry, idx) => (
              <div key={idx} className={`bubble ${entry.role}`}>
                <span className="role">{entry.role === 'user' ? 'You' : 'Coach'}</span>
                <p>{entry.text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Bottom Section: Recommendations */}
        <section className="panel" style={{ gridColumn: '1 / -1' }}>
          <h2>Suggested Actions</h2>
          {recommended.length === 0 ? (
            <p className="muted">Check in to see tailored recommendations.</p>
          ) : (
            <ul className="pill-list">
              {recommended.map((item, idx) => <li key={idx}>{item}</li>)}
            </ul>
          )}
        </section>
      </main>
    </div>
  )
}

export default App