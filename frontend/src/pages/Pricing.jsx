import { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';

export default function Pricing() {
  const { api } = useApi();
  const [billingCycle, setBillingCycle] = useState('mois');
  const [hoveredPlan, setHoveredPlan] = useState(null);

  const plans = {
    base: {
      name: 'Yêu Thương',
      price: billingCycle === 'mois' ? 290000 : 2900000,
      credits: 200000,
      unitPerCredit: 1.45,
      currency: billingCycle === 'mois' ? '/tháng' : '/năm',
      features: [
        '200.000 credits mỗi tháng',
        'STT, TTS, Dịch thuật không giới hạn',
        'Giọng đọc tiếng Việt',
        'Tạo giọng clone với 5-8 mẫu',
        'Hỗ trợ email 24/7',
        'Export kết quả (SRT, TXT, MP3, MP4)',
      ],
      popular: true,
      color: 'var(--primary)',
    },
    pro: {
      name: 'Thương Quan',
      price: billingCycle === 'mois' ? 990000 : 9900000,
      credits: 1000000,
      unitPerCredit: 0.99,
      currency: billingCycle === 'mois' ? '/tháng' : '/năm',
      features: [
        '1.000.000 credits mỗi tháng',
        'Ưu tiên hàng đầu',
        'Tăng giới hạn file (500MB/file)',
        'Tất cả giọng đọc (bao gồm cả tiếng Anh)',
        'Tạo video AI (beta)',
        'API hỗ trợ làm phiến',
        'Hỗ trợ ZO 优先',
      ],
      popular: false,
      color: 'var(--accent)',
    },
    enterprise: {
      name: 'Doanh Nghiệp',
      price: 'Tùy chỉnh',
      credits: 'Không giới hạn',
      unitPerCredit: 0,
      currency: null,
      features: [
        'Gói credit không giới hạn',
        'Host riêng & Security',
        'Hỗ trợ SLA 99.9%',
        'Custom branding',
        'Integrations on-premise',
        'Custom model hub',
        'Dedicated manager',
      ],
      popular: false,
      color: 'var(--info)',
      contact: true,
    },
  };

  const perJobCredits = {
    tts: 30,
    stt: 20,
    translate: 15,
    subtitle: 25,
    dub: 150,
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '48px' }}>
        <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '16px', fontWeight: 700 }}>
          Gói Dịch Vụ & Giá
        </h1>
        <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-lg)', marginBottom: '32px' }}>
          Lựa chọn gói phù hợp với nhu cầu của bạn
        </p>
        <div style={{ display: 'inline-flex', background: 'var(--bg)', borderRadius: 'var(--radius-md)', padding: '4px' }}>
          <button
            onClick={() => setBillingCycle('mois')}
            style={{
              padding: '8px 24px',
              borderRadius: 'var(--radius)',
              background: billingCycle === 'mois' ? 'var(--surface)' : 'transparent',
              color: billingCycle === 'mois' ? 'var(--text)' : 'var(--text-dim)',
              border: 'none',
              fontSize: 'var(--text-base)',
              fontWeight: billingCycle === 'mois' ? 600 : 400,
              cursor: 'pointer',
            }}
          >
            Thanh toán hàng tháng
          </button>
          <button
            onClick={() => setBillingCycle('năm')}
            style={{
              padding: '8px 24px',
              borderRadius: 'var(--radius)',
              background: billingCycle === 'năm' ? 'var(--surface)' : 'transparent',
              color: billingCycle === 'năm' ? 'var(--text)' : 'var(--text-dim)',
              border: 'none',
              fontSize: 'var(--text-base)',
              fontWeight: billingCycle === 'năm' ? 600 : 400,
              cursor: 'pointer',
            }}
          >
            Thanh toán hàng năm (tiết kiệm 8.3%)
          </button>
        </div>
      </div>

      {/* Plans */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '32px', marginBottom: '64px' }}>
        {Object.entries(plans).map(([key, plan]) => (
          <div
            key={key}
            onMouseEnter={() => setHoveredPlan(key)}
            onMouseLeave={() => setHoveredPlan(null)}
            style={{
              background: 'var(--surface)',
              border: plan.popular ? '2px solid var(--primary)' : '1px solid var(--border)',
              borderRadius: 'var(--radius-xl)',
              padding: '32px 24px',
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              transition: 'all 0.3s',
              transform: hoveredPlan === key ? 'translateY(-8px)' : 'none',
              boxShadow: hoveredPlan === key ? 'var(--shadow-lg)' : 'var(--shadow)',
            }}
          >
            {plan.popular && (
              <div
                style={{
                  position: 'absolute',
                  top: '-14px',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  background: 'var(--gradient)',
                  color: '#fff',
                  padding: '6px 16px',
                  borderRadius: 'var(--radius-full)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 700,
                }}
              >
                Phổ biến nhất
              </div>
            )}
            <h3 style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, marginBottom: '16px', color: plan.color }}>
              {plan.name}
            </h3>
            <div style={{ marginBottom: '32px' }}>
              <div style={{ fontSize: 'var(--text-4xl)', fontWeight: 800, color: 'var(--text)', display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                {typeof plan.price === 'string' ? plan.price : plan.price.toLocaleString('vi-VN')}
                <span style={{ fontSize: 'var(--text-lg)', fontWeight: 400, color: 'var(--text-dim)' }}>
                  {plan.currency}
                </span>
              </div>
              {plan.unitPerCredit > 0 && (
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginTop: '4px' }}>
                  {(plan.unitPerCredit).toLocaleString('vi-VN')}đ / credit
                </div>
              )}
            </div>
            <div style={{ marginBottom: '32px', flex: 1, display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: 'var(--text-base)', color: 'var(--text)' }}>
                <span style={{ fontSize: '18px' }}>💎</span>
                <span style={{ fontWeight: 600 }}>{typeof plan.credits === 'string' ? plan.credits : plan.credits.toLocaleString('vi-VN')} credits/get tháng</span>
              </div>
              {plan.features.map((feature) => (
                <div key={feature} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', fontSize: 'var(--text-sm)', color: 'var(--text)' }}>
                  <span style={{ fontSize: '16px', marginTop: '2px' }}>✓</span>
                  <span>{feature}</span>
                </div>
              ))}
            </div>
            <button
              style={{
                background: plan.popular ? 'var(--gradient)' : 'var(--bg)',
                color: plan.popular ? '#fff' : 'var(--text)',
                border: plan.popular ? 'none' : '1px solid var(--border)',
                padding: '14px 24px',
                borderRadius: 'var(--radius)',
                fontSize: 'var(--text-base)',
                fontWeight: 600,
                cursor: 'pointer',
                width: '100%',
                textAlign: 'center',
              }}
            >
              {plan.contact ? 'Liên hệ' : 'Bắt dùng'}
            </button>
          </div>
        ))}
      </div>

      {/* Credit consumption table */}
      <div style={{ marginTop: '64px' }}>
        <h2 style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, marginBottom: '24px', textAlign: 'center' }}>
          Credit tiêu thụ theo loại Job
        </h2>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-base)' }}>
            <thead style={{ background: 'var(--bg)', borderBottom: '2px solid var(--border)' }}>
              <tr>
                <th style={{ padding: '16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Loại job</th>
                <th style={{ padding: '16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Mô tả</th>
                <th style={{ padding: '16px', textAlign: 'center', fontWeight: 600, color: 'var(--text-dim)' }}>Credit/phút</th>
                <th style={{ padding: '16px', textAlign: 'center', fontWeight: 600, color: 'var(--text-dim)' }}>Ví dụ (5 phút)</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '16px', fontWeight: 600 }}>TTS</td>
                <td style={{ padding: '16px' }}>Chuyển văn bản thành giọng nói</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.tts}</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.tts * 5}</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '16px', fontWeight: 600 }}>STT</td>
                <td style={{ padding: '16px' }}>Chuyển giọng nói thành văn bản</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.stt}</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.stt * 5}</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '16px', fontWeight: 600 }}>Dịch thuật</td>
                <td style={{ padding: '16px' }}>Dịch văn bản giữa ngôn ngữ</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.translate}</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.translate * 5}</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '16px', fontWeight: 600 }}>Phụ đề</td>
                <td style={{ padding: '16px' }}>Tạo phụ đề tự động từ video</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.subtitle}</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.subtitle * 5}</td>
              </tr>
              <tr>
                <td style={{ padding: '16px', fontWeight: 600 }}>Dịch Audio/Video</td>
                <td style={{ padding: '16px' }}>Dịch đầy đủ + tạo giọng mới</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.dub}</td>
                <td style={{ padding: '16px', textAlign: 'center' }}>{perJobCredits.dub * 5}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* FAQ */}
      <div style={{ marginTop: '64px' }}>
        <h2 style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, marginBottom: '32px', textAlign: 'center' }}>
          Câu hỏi thường gặp
        </h2>
        <div style={{ display: 'grid', gap: '24px' }}>
          {[
            {
              q: 'Credit có tồn tại không?',
              a: 'Credit không có hiệu lực, bạn phải dùng within billing period of your plan.',
            },
            {
              q: 'Làm thế nào để mua thêm credit?',
              a: 'Bạn có thể mua thêm credit bất lúc nào từ dashboard. Add-on credits sẽ được cộng vào gói hiện tại và có hạn sử dụng như bình thường.',
            },
            {
              q: 'Có gói dùng thử không?',
              a: 'Mới người dùng sẽ được miễn 50.000 credits trong 7 ngày đầu tiên để làm quen features.',
            },
            {
              q: 'Thay đổi gói như thế nào?',
              a: 'Bạn có thể nâng cấp hoặc hạ cấp mỗi time. Khi nâng cấp, phần còn lại sẽ được tính pro rata; khi hạ cấp sẽ hiệu lực từ kỳ sau.',
            },
            {
              q: 'Hỗ trợ qua kênh nào?',
              a: 'Yêu Thương: Email 24/7. Thương Quan & Doanh nghiệp: ZO + dedicated support manager.',
            },
          ].map((faq, i) => (
            <div
              key={i}
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: '24px',
              }}
            >
              <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: '12px', color: 'var(--primary)' }}>
                {faq.q}
              </h3>
              <p style={{ color: 'var(--text)' }}>{faq.a}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}