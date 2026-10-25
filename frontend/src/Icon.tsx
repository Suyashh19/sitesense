import { AlertTriangle, Check, CheckCircle2, Dumbbell, FileText, FlaskConical, Info, Map as MapIcon, MapPin, MessageSquare, Pill, Play, RefreshCw, Search,
  Settings, Shirt, Smartphone, Store, UtensilsCrossed, X } from 'lucide-react'
import type { LucideProps } from 'lucide-react'

const ICONS = {
  sports: Dumbbell, food: UtensilsCrossed, fashion: Shirt, pharmacy: Pill, electronics: Smartphone,   // business categories (names come from categories.yaml)
  warning: AlertTriangle, close: X, ask: MessageSquare, pin: MapPin, search: Search, refresh: RefreshCw, build: Settings, done: CheckCircle2,
  estimate: Info, check: Check, plan: MapIcon, run: Play, brief: FileText, whatif: FlaskConical, rival: Store, store: Store,
}
export type IconName = keyof typeof ICONS

/** One place for every icon in the app (Lucide, outline style, inherits the text colour). Unknown names render a neutral store icon. */
export function Icon({ name, size = 16, ...rest }: { name: string; size?: number } & Omit<LucideProps, 'size'>) {
  const C = (ICONS as Record<string, typeof Store>)[name] ?? Store
  return <C size={size} strokeWidth={2} aria-hidden="true" style={{ verticalAlign: '-3px', flexShrink: 0, ...rest.style }} {...rest} />
}
