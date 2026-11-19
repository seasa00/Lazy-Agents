'use client';

import { RoundedBox } from '@react-three/drei';
import { ManagerAgent } from './agents/ManagerAgent';
import { DeveloperAgent } from './agents/DeveloperAgent';
import { ReviewerAgent } from './agents/ReviewerAgent';
import { Chair } from './furniture/Chair';
import { Desk } from './furniture/Desk';
import { Monitor } from './furniture/Monitor';
import { Plant } from './furniture/Plant';
import { Shelf } from './furniture/Shelf';
import { OfficeLighting } from './lighting/OfficeLighting';
import type { OfficeTheme } from './types';

export function OfficeScene3D({ theme }: { theme: OfficeTheme }) {
  const night = theme === 'night';
  return (
    <>
      <color attach="background" args={[night ? '#29394b' : '#c9d0c8']} />
      <OfficeLighting theme={theme} />
      <RoomShell night={night} />
      <RoomWallDetails night={night} />
      <Workstations theme={theme} />
    </>
  );
}

function RoomShell({ night }: { night: boolean }) {
  return (
    <group>
      <RoundedBox
        position={[0, -0.2, 0]}
        args={[12.4, 0.38, 8.8]}
        radius={0.2}
        smoothness={3}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial
          color={night ? '#554a46' : '#927354'}
          roughness={0.96}
        />
      </RoundedBox>
      <RoundedBox
        position={[0, 0.03, 0]}
        args={[12.05, 0.12, 8.45]}
        radius={0.12}
        smoothness={3}
        receiveShadow
      >
        <meshStandardMaterial
          color={night ? '#414c55' : '#d4c4a8'}
          roughness={0.93}
        />
      </RoundedBox>
      <RoundedBox
        position={[0, 2.23, -4.23]}
        args={[12.05, 4.32, 0.22]}
        radius={0.12}
        smoothness={3}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial
          color={night ? '#536176' : '#d8d0bd'}
          roughness={0.94}
        />
      </RoundedBox>
      <RoundedBox
        position={[-6.02, 2.12, 0]}
        args={[0.22, 4.1, 8.42]}
        radius={0.11}
        smoothness={2}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial
          color={night ? '#47566a' : '#c7c1af'}
          roughness={0.95}
        />
      </RoundedBox>
      <RoundedBox
        position={[0, -0.37, 0]}
        args={[12.48, 0.15, 8.88]}
        radius={0.1}
        smoothness={2}
      >
        <meshStandardMaterial
          color={night ? '#344352' : '#b39672'}
          roughness={0.9}
        />
      </RoundedBox>
      <mesh position={[0, 0.105, 2.2]} scale={[1, 1, 0.58]} receiveShadow>
        <cylinderGeometry args={[2.08, 2.08, 0.025, 32]} />
        <meshStandardMaterial
          color={night ? '#64747b' : '#aaa58e'}
          roughness={1}
        />
      </mesh>
      <mesh position={[0, 0.22, 2.2]} castShadow>
        <cylinderGeometry args={[0.075, 0.09, 0.25, 8]} />
        <meshStandardMaterial
          color={night ? '#594d45' : '#967354'}
          roughness={0.92}
        />
      </mesh>
      <mesh
        position={[0, 0.37, 2.2]}
        scale={[1, 1, 0.72]}
        castShadow
        receiveShadow
      >
        <cylinderGeometry args={[0.64, 0.61, 0.075, 10]} />
        <meshStandardMaterial
          color={night ? '#866749' : '#ab805a'}
          roughness={0.9}
        />
      </mesh>
      <mesh position={[0.22, 0.46, 2.14]} castShadow>
        <cylinderGeometry args={[0.065, 0.07, 0.1, 8]} />
        <meshStandardMaterial
          color={night ? '#e0c18d' : '#e5d5bc'}
          roughness={0.86}
        />
      </mesh>
    </group>
  );
}

function RoomWallDetails({ night }: { night: boolean }) {
  const board = night ? '#65736c' : '#a9aa8e';
  const frame = night ? '#6e6254' : '#9b7655';
  return (
    <group>
      <RoundedBox
        position={[0.15, 2.42, -4.09]}
        args={[2.65, 1.58, 0.08]}
        radius={0.08}
        smoothness={2}
        castShadow
      >
        <meshStandardMaterial color={frame} roughness={0.88} />
      </RoundedBox>
      <RoundedBox
        position={[0.15, 2.42, -4.035]}
        args={[2.42, 1.35, 0.035]}
        radius={0.04}
        smoothness={2}
      >
        <meshStandardMaterial color={board} roughness={0.97} />
      </RoundedBox>
      {[
        [-0.53, 2.72, '#d0a275', 0.62],
        [0.21, 2.72, '#85947b', 0.72],
        [-0.32, 2.28, '#8c96a2', 0.88],
        [0.57, 2.31, '#cfb27e', 0.46],
      ].map(([x, y, color, width], index) => (
        <RoundedBox
          key={index}
          position={[Number(x), Number(y), -3.99]}
          args={[Number(width), 0.07, 0.025]}
          radius={0.025}
          smoothness={1}
        >
          <meshStandardMaterial color={String(color)} roughness={0.9} />
        </RoundedBox>
      ))}
      <PlanningNote position={[-0.73, 2.02, -3.985]} night={night} />
      <PlanningNote position={[0.97, 2.63, -3.985]} night={night} />
      <Window position={[4.22, 2.53, -4.075]} night={night} />
      <Shelf position={[-5.1, 0, -3.73]} night={night} />
      <Plant position={[-5.15, 0, 3.05]} night={night} scale={1.04} />
      <Plant position={[5.12, 0, 3.04]} night={night} scale={0.86} />
      <Plant position={[5.2, 0, -3.45]} night={night} scale={0.7} />
      <WallLamp position={[-2.3, 2.12, -4.04]} night={night} />
    </group>
  );
}

function PlanningNote({
  position,
  night,
}: {
  position: [number, number, number];
  night: boolean;
}) {
  return (
    <group position={position}>
      <RoundedBox
        args={[0.36, 0.42, 0.035]}
        radius={0.025}
        smoothness={1}
        rotation={[0, 0, -0.12]}
      >
        <meshStandardMaterial
          color={night ? '#c3ae85' : '#e8ddc5'}
          roughness={0.95}
        />
      </RoundedBox>
      <mesh position={[0, 0.03, 0.024]}>
        <boxGeometry args={[0.19, 0.025, 0.012]} />
        <meshStandardMaterial color="#82917d" roughness={0.9} />
      </mesh>
      <mesh position={[0, -0.06, 0.024]}>
        <boxGeometry args={[0.23, 0.022, 0.012]} />
        <meshStandardMaterial color="#a98566" roughness={0.9} />
      </mesh>
    </group>
  );
}

function Window({
  position,
  night,
}: {
  position: [number, number, number];
  night: boolean;
}) {
  const frame = night ? '#947b62' : '#a67b57';
  return (
    <group position={position}>
      <RoundedBox
        args={[2.55, 2.03, 0.12]}
        radius={0.09}
        smoothness={2}
        castShadow
      >
        <meshStandardMaterial color={frame} roughness={0.83} />
      </RoundedBox>
      <RoundedBox
        position={[0, 0, 0.072]}
        args={[2.31, 1.78, 0.025]}
        radius={0.045}
        smoothness={2}
      >
        <meshStandardMaterial
          color={night ? '#34475b' : '#9fb8ba'}
          emissive={night ? '#d49a5e' : '#63828a'}
          emissiveIntensity={night ? 0.32 : 0.1}
          roughness={0.7}
        />
      </RoundedBox>
      {night && (
        <>
          {[-0.61, 0.21, 0.67].map((x, i) => (
            <RoundedBox
              key={i}
              position={[x, i === 1 ? -0.33 : 0.22, 0.092]}
              args={[0.28, 0.39, 0.014]}
              radius={0.025}
              smoothness={1}
            >
              <meshStandardMaterial
                color={i === 1 ? '#d3a671' : '#c7945c'}
                emissive="#bb8750"
                emissiveIntensity={0.6}
                roughness={0.7}
              />
            </RoundedBox>
          ))}
        </>
      )}
      <mesh position={[0, 0, 0.105]}>
        <boxGeometry args={[0.07, 1.8, 0.045]} />
        <meshStandardMaterial color={frame} roughness={0.84} />
      </mesh>
      <mesh position={[0, 0, 0.105]}>
        <boxGeometry args={[2.3, 0.065, 0.045]} />
        <meshStandardMaterial color={frame} roughness={0.84} />
      </mesh>
    </group>
  );
}

function Workstations({ theme }: { theme: OfficeTheme }) {
  const night = theme === 'night';
  return (
    <group>
      <Desk
        position={[0, 0, -1.72]}
        width={2.8}
        depth={1.2}
        drawerSide="right"
        night={night}
      />
      <Chair position={[0, 0, -0.24]} color={night ? '#667268' : '#82917d'} />
      <Monitor
        position={[-0.22, 0, -2.08]}
        width={0.98}
        mode="plan"
        theme={theme}
      />
      <ManagerAgent position={[0, 0, -0.74]} />
      <Clipboard position={[-0.82, 1.04, -1.35]} night={night} />
      <DeskLamp position={[0.88, 0.98, -1.42]} night={night} />

      <Desk
        position={[-3.22, 0, 0.82]}
        width={3.25}
        depth={1.28}
        night={night}
      />
      <Chair
        position={[-3.22, 0, 2.34]}
        color={night ? '#4b5f73' : '#536887'}
      />
      <Monitor
        position={[-3.87, 0, 0.47]}
        width={0.88}
        mode="code"
        theme={theme}
      />
      <Monitor
        position={[-2.83, 0, 0.47]}
        width={0.88}
        mode="code"
        theme={theme}
      />
      <DeveloperAgent position={[-3.22, 0, 1.82]} />
      <Keyboard position={[-3.22, 1.04, 1.15]} night={night} />
      <DeskLamp position={[-4.48, 0.98, 0.53]} night={night} />

      <Desk
        position={[3.22, 0, 0.82]}
        width={2.86}
        depth={1.18}
        drawerSide="left"
        night={night}
      />
      <Chair position={[3.22, 0, 2.29]} color={night ? '#756a71' : '#9b7b70'} />
      <Monitor
        position={[3.22, 0, 0.48]}
        width={0.98}
        mode="review"
        theme={theme}
      />
      <ReviewerAgent position={[3.22, 0, 1.77]} />
      <DocumentStack position={[4.1, 1.04, 1.12]} night={night} />
      <Clipboard position={[2.25, 1.04, 1.13]} night={night} />
      <DeskLamp position={[4.35, 0.98, 0.47]} night={night} />
    </group>
  );
}

function Clipboard({
  position,
  night,
}: {
  position: [number, number, number];
  night: boolean;
}) {
  return (
    <group position={position} rotation={[-0.08, 0, -0.1]}>
      <RoundedBox args={[0.46, 0.055, 0.58]} radius={0.035} smoothness={2}>
        <meshStandardMaterial
          color={night ? '#bdad91' : '#e2d5bb'}
          roughness={0.94}
        />
      </RoundedBox>
      <mesh position={[0, 0.034, -0.13]}>
        <boxGeometry args={[0.17, 0.018, 0.025]} />
        <meshStandardMaterial color="#87947f" roughness={0.9} />
      </mesh>
      {[0, 1, 2].map((row) => (
        <mesh key={row} position={[-0.03, 0.035, -0.03 + row * 0.11]}>
          <boxGeometry args={[0.22, 0.018, 0.018]} />
          <meshStandardMaterial
            color={row === 2 ? '#c08360' : '#8d9888'}
            roughness={0.9}
          />
        </mesh>
      ))}
    </group>
  );
}

function Keyboard({
  position,
  night,
}: {
  position: [number, number, number];
  night: boolean;
}) {
  return (
    <group position={position}>
      <RoundedBox args={[1.02, 0.07, 0.32]} radius={0.055} smoothness={2}>
        <meshStandardMaterial
          color={night ? '#384650' : '#505a5c'}
          roughness={0.82}
        />
      </RoundedBox>
      {[0, 1, 2].map((row) => (
        <mesh key={row} position={[0, 0.04, -0.08 + row * 0.07]}>
          <boxGeometry args={[0.78 - row * 0.04, 0.018, 0.025]} />
          <meshStandardMaterial
            color={row === 1 ? '#87aa9c' : '#a9b2ad'}
            roughness={0.84}
          />
        </mesh>
      ))}
    </group>
  );
}

function DocumentStack({
  position,
  night,
}: {
  position: [number, number, number];
  night: boolean;
}) {
  return (
    <group position={position} rotation={[0, 0.1, -0.06]}>
      {[0, 1, 2].map((index) => (
        <RoundedBox
          key={index}
          position={[0, index * 0.035, -index * 0.025]}
          args={[0.52, 0.035, 0.66]}
          radius={0.025}
          smoothness={1}
        >
          <meshStandardMaterial
            color={night ? '#c9bca4' : '#eee5d4'}
            roughness={0.96}
          />
        </RoundedBox>
      ))}
      <mesh position={[-0.14, 0.105, -0.11]}>
        <boxGeometry args={[0.19, 0.012, 0.025]} />
        <meshStandardMaterial color="#8a9b82" roughness={0.9} />
      </mesh>
      <mesh position={[-0.14, 0.105, -0.01]}>
        <boxGeometry args={[0.24, 0.012, 0.025]} />
        <meshStandardMaterial color="#9c846d" roughness={0.9} />
      </mesh>
      <mesh position={[-0.14, 0.105, 0.09]}>
        <boxGeometry args={[0.17, 0.012, 0.025]} />
        <meshStandardMaterial color="#9c846d" roughness={0.9} />
      </mesh>
    </group>
  );
}

function DeskLamp({
  position,
  night,
}: {
  position: [number, number, number];
  night: boolean;
}) {
  return (
    <group position={position}>
      <mesh position={[0, 0.06, 0]}>
        <cylinderGeometry args={[0.22, 0.25, 0.07, 10]} />
        <meshStandardMaterial
          color={night ? '#9e886c' : '#85705b'}
          roughness={0.76}
        />
      </mesh>
      <mesh position={[0, 0.42, -0.04]} rotation={[0, 0, -0.2]}>
        <cylinderGeometry args={[0.045, 0.055, 0.64, 8]} />
        <meshStandardMaterial color="#75644f" roughness={0.72} />
      </mesh>
      <mesh position={[0.06, 0.74, -0.1]} rotation={[0, 0, 0.2]}>
        <coneGeometry args={[0.27, 0.34, 8]} />
        <meshStandardMaterial
          color={night ? '#d5a66e' : '#cdbb9e'}
          emissive={night ? '#d69a53' : '#000000'}
          emissiveIntensity={night ? 0.4 : 0}
          roughness={0.87}
        />
      </mesh>
    </group>
  );
}

function WallLamp({
  position,
  night,
}: {
  position: [number, number, number];
  night: boolean;
}) {
  return (
    <group position={position}>
      <mesh position={[0, 0, 0.08]}>
        <cylinderGeometry args={[0.2, 0.2, 0.08, 8]} />
        <meshStandardMaterial
          color={night ? '#d3a66e' : '#c6b594'}
          emissive={night ? '#c99256' : '#000000'}
          emissiveIntensity={night ? 0.35 : 0}
          roughness={0.9}
        />
      </mesh>
      <mesh position={[0, -0.24, 0.1]}>
        <coneGeometry args={[0.33, 0.35, 8]} />
        <meshStandardMaterial
          color={night ? '#dab47e' : '#d8cbb1'}
          emissive={night ? '#bf8b4f' : '#000000'}
          emissiveIntensity={night ? 0.42 : 0}
          roughness={0.9}
        />
      </mesh>
    </group>
  );
}
