"""Shared SVG face geometry for the car illustrations."""
from xml.etree import ElementTree as ET


def add_expression(car, index):
    for node in list(car):
        tag = node.tag.rsplit('}', 1)[-1]
        if tag == 'circle' or (tag == 'path' and node.get('d', '').startswith(('M45', 'm36'))):
            car.remove(node)
    eye_y, mouth_y = (34, 77) if index == 1 else (31, 69)
    face = ET.SubElement(car, 'g', {'class': 'car-expression', 'data-eye-y': str(eye_y), 'data-mouth-y': str(mouth_y)})
    for side, x in (('left', 40), ('right', 70)):
        ET.SubElement(face, 'path', {'class': f'face-eye-{side}', 'd': f'M{x} {eye_y}v1', 'fill': 'none', 'stroke': '#1B2340', 'stroke-width': '4'})
        ET.SubElement(face, 'path', {'class': 'face-tear', 'd': f'M{x} {eye_y+5}q-5 8 0 10q5-2 0-10Z', 'fill': '#38BDF8', 'stroke': 'none', 'visibility': 'hidden'})
    ET.SubElement(face, 'path', {'class': 'face-mouth', 'd': f'M45 {mouth_y}q10 7 20 0', 'fill': 'none', 'stroke': '#FFFFFF' if index == 0 else '#1B2340', 'stroke-width': '3'})


FACE_JS = r"""
function setCarFace(root, mood) {
  root.querySelectorAll('.car-expression').forEach(face => {
    const eyeY = Number(face.dataset.eyeY), mouthY = Number(face.dataset.mouthY);
    ['left','right'].forEach((side, i) => {
      const x = i ? 70 : 40;
      face.querySelector('.face-eye-' + side).setAttribute('d', mood === 'happy'
        ? `M${x-4} ${eyeY+1}q4-7 8 0`
        : mood === 'crying' ? `M${x-4} ${eyeY-1}l8 ${i ? -3 : 3}` : `M${x} ${eyeY}v1`);
    });
    const mouth = face.querySelector('.face-mouth');
    mouth.setAttribute('d', mood === 'happy' ? `M43 ${mouthY-2}q12 21 24 0Z`
      : mood === 'crying' ? `M45 ${mouthY+6}q10-12 20 0` : `M45 ${mouthY}q10 7 20 0`);
    mouth.setAttribute('fill', mood === 'happy' ? '#FF7A66' : 'none');
    face.querySelectorAll('.face-tear').forEach(tear => tear.setAttribute('visibility', mood === 'crying' ? 'visible' : 'hidden'));
    face.dataset.mood = mood;
  });
}
"""
