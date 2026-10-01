import PromptLibrary from './prompts/PromptLibrary.jsx';

// Trang "Prompt của tôi" — mọi user đăng nhập. Nội dung nằm trong
// PromptLibrary (component dùng chung với tab trong AI Model Hub).
export default function Prompts() {
  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <PromptLibrary />
    </div>
  );
}
