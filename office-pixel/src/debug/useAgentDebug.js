import { useEffect, useRef, useState } from 'react'
import { initialSnapshots, applyTransition } from './mockData.js'

// DEV-ONLY adapter: office pose changes -> mock snapshots with appended trace entries.
// A production adapter would instead subscribe to the Lazy Agents backend and return real snapshots
// with the same AgentDebugSnapshot shape (see contract.js). The inspector does not care.
export function useAgentDebug(agentPoses) {
  const poses = { manager: agentPoses.manager.pose, developer: agentPoses.developer.pose, reviewer: agentPoses.reviewer.pose }
  const [snaps, setSnaps] = useState(() => initialSnapshots(poses))
  const prev = useRef(poses)
  useEffect(() => {
    for (const id of Object.keys(poses)) {
      if (poses[id] !== prev.current[id]) setSnaps((s) => ({ ...s, [id]: applyTransition(s[id], id, poses[id]) }))
    }
    prev.current = poses
  }, [poses.manager, poses.developer, poses.reviewer]) // eslint-disable-line react-hooks/exhaustive-deps
  return snaps
}
