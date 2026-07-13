import { create } from 'zustand'

type AppStore = {
  selectedRosterId: number | null
  setSelectedRosterId: (id: number | null) => void
  commandOpen: boolean
  setCommandOpen: (open: boolean) => void
}

export const useAppStore = create<AppStore>((set) => ({
  selectedRosterId: null,
  setSelectedRosterId: (id) => set({ selectedRosterId: id }),
  commandOpen: false,
  setCommandOpen: (open) => set({ commandOpen: open }),
}))
