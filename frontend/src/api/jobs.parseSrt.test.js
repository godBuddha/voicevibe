// GD3 — vitest: parseSrt là bộ phân tích phụ đề cốt lõi (trang Phụ đề/STT đọc
// cue từ đây); hai dạng prefix người nói + hai kiểu dấu thời gian đều phải đúng.
import { describe, it, expect } from 'vitest';
import { parseSrt } from './jobs.js';

describe('parseSrt', () => {
  it('SRT chuẩn: block, chỉ số, dấu phẩy milli', () => {
    const cues = parseSrt(
      '1\n00:00:01,500 --> 00:00:02,500\nXin chào\n\n' +
      '2\n00:00:03,000 --> 00:00:04,200\nHai dòng\nnối nhau\n\n');
    expect(cues).toHaveLength(2);
    expect(cues[0]).toEqual({ start: 1.5, end: 2.5, text: 'Xin chào', speaker: '' });
    expect(cues[1].text).toBe('Hai dòng\nnối nhau');
  });

  it('CRLF + dấu chấm VTT', () => {
    const cues = parseSrt('1\r\n00:00:01.000 --> 00:00:02.000\r\nA\r\n\r\n');
    expect(cues[0]).toMatchObject({ start: 1, end: 2, text: 'A' });
  });

  it('speaker dạng [SPEAKER_00] (stt.to_srt)', () => {
    const cues = parseSrt('1\n00:00:00,000 --> 00:00:01,000\n[SPEAKER_00] lời nói\n\n');
    expect(cues[0].speaker).toBe('SPEAKER_00');
    expect(cues[0].text).toBe('lời nói');
  });

  it('speaker dạng "SPEAKER_00: " (subtitle.build_cues)', () => {
    const cues = parseSrt('1\n00:00:00,000 --> 00:00:01,000\nSPEAKER_01: another line\n\n');
    expect(cues[0].speaker).toBe('SPEAKER_01');
    expect(cues[0].text).toBe('another line');
  });

  it('block thiếu --> bị bỏ qua, input rỗng → mảng rỗng', () => {
    expect(parseSrt('rác không cấu trúc')).toHaveLength(0);
    expect(parseSrt('')).toHaveLength(0);
  });
});
