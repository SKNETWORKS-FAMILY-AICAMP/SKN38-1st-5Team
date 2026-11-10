const instances = new WeakMap();
export default function ({parentElement, data, setStateValue}) {
  let state = instances.get(parentElement);
  if (!state) {
    const frame = document.createElement('iframe');
    frame.title = '주차장·충전소 위치 지도';
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox');
    frame.style.cssText = 'width:100%;height:510px;border:0;display:block';
    parentElement.append(frame);
    state = {frame, html:null, data, setStateValue};
    state.listener = event => {
      if (event.source !== frame.contentWindow || event.data?.type !== 'chachacha-place') return;
      const id = event.data.id;
      if (typeof id !== 'string' || !state.data.ids.includes(id)) return;
      state.setStateValue('selected_place', {id});
    };
    window.addEventListener('message', state.listener);
    instances.set(parentElement, state);
  }
  state.data = data;
  state.setStateValue = setStateValue;
  if (state.html !== data.html) {
    state.html = data.html;
    state.frame.srcdoc = data.html;
  }
  return () => {
    window.removeEventListener('message', state.listener);
    state.frame.remove();
    instances.delete(parentElement);
  };
}
