// The room shell is authored pixel art. People and furniture are independent
// transparent sprites layered above it in shared panorama coordinates.
export function OfficeRoom() {
  return (
    <div
      className="office-room"
      data-room-system="authored-sprites"
      aria-hidden="true"
    >
      <span className="office-plant plant-left" data-room-object="plant" />
      <span className="office-plant plant-right" data-room-object="plant" />
      <span className="workflow-path path-first">···→</span>
      <span className="workflow-path path-second">···→</span>
    </div>
  );
}
