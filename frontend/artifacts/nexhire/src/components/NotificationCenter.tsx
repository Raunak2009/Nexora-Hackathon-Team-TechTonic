import { useState } from 'react';
import {
  Bell, CheckCircle2, AlertTriangle, Sparkles,
  FileDown, Clock, X, ExternalLink
} from 'lucide-react';
import { Link } from 'wouter';

interface NotificationItem {
  id: string;
  title: string;
  description: string;
  time: string;
  type: 'success' | 'alert' | 'info';
  read: boolean;
  link?: string;
}

const INITIAL_NOTIFICATIONS: NotificationItem[] = [
  {
    id: 'notif-1',
    title: 'AI Resume Evaluation Completed',
    description: '10 candidate resumes screened and ranked with 95% model confidence.',
    time: '4 mins ago',
    type: 'success',
    read: false,
    link: '/',
  },
  {
    id: 'notif-2',
    title: 'Top Candidate Identified',
    description: 'Aarav Mehta scored 94% fit with strong evidence in React & TypeScript at Microsoft.',
    time: '18 mins ago',
    type: 'info',
    read: false,
    link: '/candidate/cand-1',
  },
  {
    id: 'notif-3',
    title: 'Chronological Flag Detected',
    description: 'Candidate Neha Kapoor flagged for 18-month unverified career gap.',
    time: '1 hr ago',
    type: 'alert',
    read: false,
    link: '/candidate/cand-6',
  },
  {
    id: 'notif-4',
    title: 'Job Description Bias Audit Passed',
    description: 'Zero unlawful age or gender bias triggers found in active role description.',
    time: '2 hrs ago',
    type: 'success',
    read: false,
    link: '/jobs',
  },
];

interface NotificationCenterProps {
  isOpen: boolean;
  onClose: () => void;
}

export function NotificationCenter({ isOpen, onClose }: NotificationCenterProps) {
  const [notifications, setNotifications] = useState<NotificationItem[]>(INITIAL_NOTIFICATIONS);

  if (!isOpen) return null;

  const markAllAsRead = () => {
    setNotifications(notifications.map((n) => ({ ...n, read: true })));
  };

  const clearNotification = (id: string) => {
    setNotifications(notifications.filter((n) => n.id !== id));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end p-4 pt-16 sm:p-6 sm:pt-20 bg-black/40 backdrop-blur-[2px]">
      <div className="w-full max-w-sm rounded-xl border border-[#2B4F71] bg-[#102740] shadow-2xl animate-rise-in">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#24415C] px-4 py-3.5">
          <div className="flex items-center gap-2">
            <Bell size={15} className="text-[#4A9FE0]" />
            <h4 className="text-[13px] font-bold text-white">Notifications</h4>
            <span className="rounded-full bg-[#4A9FE0]/20 px-1.5 py-0.2 text-[9px] font-bold text-[#6AB7E8]">
              {notifications.filter((n) => !n.read).length} new
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={markAllAsRead}
              className="text-[10px] text-[#7195AE] hover:text-white"
            >
              Mark all read
            </button>
            <button onClick={onClose} className="text-[#7195AE] hover:text-white">
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Notifications List */}
        <div className="max-h-[380px] overflow-y-auto divide-y divide-[#24415C]/60">
          {notifications.length === 0 ? (
            <div className="p-8 text-center text-[11px] text-[#7896AA]">
              No active notifications.
            </div>
          ) : (
            notifications.map((notif) => (
              <div
                key={notif.id}
                className={`p-3.5 transition-colors hover:bg-[#153250] ${
                  !notif.read ? 'bg-[#142E4B]/60' : ''
                }`}
              >
                <div className="flex items-start gap-2.5">
                  <div className="mt-0.5">
                    {notif.type === 'success' && (
                      <CheckCircle2 size={14} className="text-[#3FB27F]" />
                    )}
                    {notif.type === 'alert' && (
                      <AlertTriangle size={14} className="text-[#FBBF24]" />
                    )}
                    {notif.type === 'info' && (
                      <Sparkles size={14} className="text-[#4A9FE0]" />
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <h5 className="text-[11px] font-bold text-[#E0EEF5]">
                        {notif.title}
                      </h5>
                      <span className="text-[9px] text-[#69889E] flex items-center gap-1">
                        <Clock size={10} /> {notif.time}
                      </span>
                    </div>
                    <p className="mt-1 text-[10px] leading-4 text-[#98B3C5]">
                      {notif.description}
                    </p>
                    {notif.link && (
                      <Link
                        href={notif.link}
                        onClick={onClose}
                        className="mt-2 inline-flex items-center gap-1 text-[10px] font-bold text-[#4A9FE0] hover:underline"
                      >
                        View details <ExternalLink size={10} />
                      </Link>
                    )}
                  </div>
                  <button
                    onClick={() => clearNotification(notif.id)}
                    className="text-[#597B94] hover:text-[#F87171]"
                  >
                    <X size={12} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
