import ReactDOM from 'react-dom/client';

import { App } from './ui/App';
import { PresentationReplay } from './ui/PresentationReplay';
import './styles.css';

const isPresentationRoute = window.location.pathname.replace(/\/$/, '') === '/presentation';

ReactDOM.createRoot(document.getElementById('root')!).render(isPresentationRoute ? <PresentationReplay /> : <App />);
