'use client';

import { RoundedBox } from '@react-three/drei';

export type FigureStyle = {
  coat: string;
  hair: string;
  headphones?: boolean;
  bob?: boolean;
};

export function AgentFigure({
  position,
  style,
}: {
  position: [number, number, number];
  style: FigureStyle;
}) {
  return (
    <group position={position}>
      <RoundedBox
        position={[0, 1.02, 0]}
        args={[0.64, 0.82, 0.42]}
        radius={0.19}
        smoothness={4}
        castShadow
      >
        <meshStandardMaterial color={style.coat} roughness={0.9} />
      </RoundedBox>
      {[-1, 1].map((side) => (
        <group
          key={side}
          position={[side * 0.35, 0.98, 0.23]}
          rotation={[0.48, 0, side * -0.42]}
        >
          <mesh castShadow>
            <capsuleGeometry args={[0.095, 0.4, 4, 8]} />
            <meshStandardMaterial color={style.coat} roughness={0.92} />
          </mesh>
          <mesh position={[0, -0.25, 0.02]} castShadow>
            <sphereGeometry args={[0.12, 10, 8]} />
            <meshStandardMaterial color="#bf9272" roughness={0.9} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, 1.68, 0.015]} castShadow>
        <sphereGeometry args={[0.31, 14, 12]} />
        <meshStandardMaterial color="#c79778" roughness={0.92} />
      </mesh>
      <mesh position={[0, style.bob ? 1.88 : 1.9, -0.035]} castShadow>
        <sphereGeometry
          args={[
            style.bob ? 0.34 : 0.315,
            12,
            8,
            0,
            Math.PI * 2,
            0,
            Math.PI * 0.52,
          ]}
        />
        <meshStandardMaterial color={style.hair} roughness={0.96} />
      </mesh>
      {style.bob && (
        <>
          {[-0.25, 0.25].map((x) => (
            <RoundedBox
              key={x}
              position={[x, 1.63, 0.01]}
              args={[0.16, 0.46, 0.2]}
              radius={0.07}
              smoothness={2}
              castShadow
            >
              <meshStandardMaterial color={style.hair} roughness={0.96} />
            </RoundedBox>
          ))}
        </>
      )}
      {style.headphones && <Headphones />}
    </group>
  );
}

function Headphones() {
  return (
    <group position={[0, 1.7, 0.02]}>
      <mesh rotation={[0, 0, Math.PI]}>
        <torusGeometry args={[0.34, 0.045, 7, 20, Math.PI]} />
        <meshStandardMaterial color="#293b4d" roughness={0.7} />
      </mesh>
      {[-0.31, 0.31].map((x) => (
        <RoundedBox
          key={x}
          position={[x, -0.02, 0]}
          args={[0.13, 0.25, 0.15]}
          radius={0.045}
          smoothness={2}
          castShadow
        >
          <meshStandardMaterial color="#273a4e" roughness={0.78} />
        </RoundedBox>
      ))}
    </group>
  );
}
