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
        ET.SubElement(face, 'path', {'class': 'face-tear', 'd': f'M{x-4} {eye_y+3}h8v20q0 9-4 10q-4-1-4-10Z', 'fill': '#38BDF8', 'stroke': '#E0F2FE', 'stroke-width': '1.5', 'visibility': 'hidden'})
        ET.SubElement(face, 'path', {'class': 'face-brow', 'd': f'M{x-6} {eye_y-7}q6 -5 12 0', 'fill': 'none', 'stroke': '#1B2340', 'stroke-width': '3', 'visibility': 'hidden'})
    ET.SubElement(face, 'path', {'class': 'face-mouth', 'd': f'M45 {mouth_y}q10 7 20 0', 'fill': 'none', 'stroke': '#FFFFFF' if index == 0 else '#1B2340', 'stroke-width': '3'})


FACE_JS = r"""
function setCarFace(root, mood) {
  root.querySelectorAll('.car-expression').forEach(face => {
    const eyeY = Number(face.dataset.eyeY), mouthY = Number(face.dataset.mouthY);
    ['left','right'].forEach((side, i) => {
      const x = i ? 70 : 40;
      face.querySelector('.face-eye-' + side).setAttribute('d', mood === 'happy'
        ? `M${x-4} ${eyeY+1}q4-7 8 0`
        : mood === 'crying' ? `M${x-6} ${eyeY-1}q6 6 12 0` : `M${x} ${eyeY}v1`);
    });
    const mouth = face.querySelector('.face-mouth');
    mouth.setAttribute('d', mood === 'happy' ? `M43 ${mouthY-2}q12 21 24 0Z`
      : mood === 'crying' ? `M42 ${mouthY+8}q13-23 26 0q-13-7-26 0Z` : `M45 ${mouthY}q10 7 20 0`);
    mouth.setAttribute('fill', mood === 'crying' ? '#1B2340' : mood === 'happy' ? '#FF7A66' : 'none');
    face.querySelectorAll('.face-brow').forEach(brow => brow.setAttribute('visibility', mood === 'crying' ? 'visible' : 'hidden'));
    face.querySelectorAll('.face-tear').forEach(tear => tear.setAttribute('visibility', mood === 'crying' ? 'visible' : 'hidden'));
    face.dataset.mood = mood;
  });
}
"""
