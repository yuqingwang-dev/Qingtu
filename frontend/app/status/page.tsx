'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
type Check = { status: string; message: string; provider?: string; model?: string };
type StatusResponse = { status: string; environment: string; checks: Record<string, Check> };
const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
export default function StatusPage() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [error, setError] = useState('');
  const [probing, setProbing] = useState(false);
  const load = async (probe = false) => {
    setError(''); if (probe) setProbing(true);
    try {
      const response = await fetch(API + '/api/v1/system/status' + (probe ? '?probe_llm=true' : ''), { cache: 'no-store' });
      if (!response.ok) throw new Error('后端状态接口不可用');
      setData(await response.json());
    } catch (cause) { setError(cause instanceof Error ? cause.message : '状态读取失败'); }
    finally { setProbing(false); }
  };
  useEffect(() => { void load(); }, []);
  return <main className='gradient-bg min-h-screen py-10'><div className='qt-container max-w-4xl space-y-6'>
    <Link href='/' className='underline'>← 返回晴途首页</Link>
    <div><p className='qt-eyebrow'>晴途运行状态</p><h1 className='text-3xl font-bold'>服务检查</h1><p className='mt-2 text-gray-600'>默认检查不调用模型；点击“验证 AI”才会发送一次真实请求。</p></div>
    {error && <p role='alert' className='text-red-700'>{error}</p>}
    {data && <><div className='glass-card rounded-2xl p-5'><p className='text-sm text-gray-600'>环境：{data.environment}</p><p className='text-xl font-bold mt-1'>整体状态：{data.status === 'healthy' ? '正常' : '有降级项'}</p></div>
      <div className='grid gap-4 md:grid-cols-2'>{Object.entries(data.checks).map(([name, check]) => <article key={name} className='glass-card rounded-2xl p-5'>
        <div className='flex justify-between gap-3'><h2 className='font-bold'>{name === 'llm' ? 'AI 模型' : name === 'amap' ? '高德服务' : name === 'live_poi' ? '真实 POI' : name === 'database' ? '数据库' : 'Redis'}</h2><span className='text-sm font-semibold'>{check.status}</span></div>
        <p className='mt-2 text-sm text-gray-600'>{check.message}</p>{check.provider && <p className='mt-2 text-xs text-gray-500'>服务商：{check.provider} · 模型：{check.model}</p>}
      </article>)}</div>
      <div className='flex flex-wrap gap-3'><button className='qt-button qt-button-primary' onClick={() => void load(true)} disabled={probing}>{probing ? '正在验证 AI…' : '验证 AI（可能消耗配额）'}</button><Link href='/knowledge' className='qt-button'>打开攻略查询</Link></div>
    </>}
  </div></main>;
}
