import { useEffect } from 'react'

export default function NetworkActivityEffects() {
  useEffect(() => {
    const update = (event: Event) => {
      const { active } = (event as CustomEvent<{ active: boolean }>).detail
      document.body.classList.toggle('pantryos-network-busy', active)
    }
    window.addEventListener('pantryos:network-activity', update)
    return () => {
      window.removeEventListener('pantryos:network-activity', update)
      document.body.classList.remove('pantryos-network-busy')
    }
  }, [])

  return null
}