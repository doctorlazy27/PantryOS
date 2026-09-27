import { useState } from 'react'
import { AlertTriangle, Bot, Sparkles } from 'lucide-react'
import { getWarehouseCopilot, Role } from './api'

type Props = { role: Role; onToast: (message: string) => void }
const prompts = ['What needs attention today?', 'Which stock needs a reorder review?', 'What batches need an expiry check?']

export default function AIHelpPanel({ role, onToast }: Props) {
  const [question, setQuestion] = useState(prompts[0])
  const [answer, setAnswer] = useState('')
  const [priorities, setPriorities] = useState<string[]>([])
  const [aiPowered, setAiPowered] = useState(false)
  const [loading, setLoading] = useState(false)

  async function ask(prompt = question) {
    setQuestion(prompt)
    setLoading(true)
    try {
      const result = await getWarehouseCopilot(prompt)
      setAnswer(result.answer)
      setPriorities(result.priorities)
      setAiPowered(result.ai_powered)
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'AI Help is unavailable')
    } finally {
      setLoading(false)
    }
  }

  return <><section className="module-header"><div><p className="eyebrow">Warehouse assistance</p><h1>AI Help</h1><p>{role === 'manager' ? 'Ask about current stock, expiry, and replenishment priorities.' : 'Get guidance from current data for your assigned warehouse.'}</p></div></section><section className="panel copilot-panel"><div className="copilot-title"><div className="scan-icon"><Bot size={21} /></div><div><h2>Warehouse assistant</h2><span>{aiPowered ? 'Model-assisted · grounded in live warehouse data' : 'Local rules fallback · model API not configured or unavailable'}</span></div></div><div className="copilot-prompts">{prompts.map((prompt) => <button key={prompt} onClick={() => void ask(prompt)}>{prompt}</button>)}</div><div className="copilot-ask"><input aria-label="Ask AI Help" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !loading) void ask() }} /><button className="button primary" disabled={loading || !question.trim()} onClick={() => void ask()}><Sparkles size={16} />{loading ? 'Thinking...' : 'Ask'}</button></div>{answer && <div className="copilot-answer"><strong>{answer}</strong>{priorities.map((priority) => <span key={priority}><AlertTriangle size={14} />{priority}</span>)}</div>}</section></>
}