import React from 'react';
import { useAuth } from '../context/AuthContext';
import { JobTable } from '../components/JobTable';
import { FilterBar } from '../components/FilterBar';
import { useJobs } from '../hooks/useJobs';

const StatCard = ({ label, value, color, icon }) => (
  <div className="glass-panel p-4 d-flex align-items-center hover-card h-100">
    <div className={`rounded-circle d-flex align-items-center justify-content-center me-3 bg-${color}-10 text-${color}`} 
         style={{ width: 48, height: 48 }}>
      <i className={`bi ${icon} fs-4`}></i>
    </div>
    <div>
      <div className="h3 fw-bold mb-0 text-white">{value}</div>
      <div className="text-secondary small fw-medium text-uppercase tracking-wide">{label}</div>
    </div>
  </div>
);

export function JobsPage() {
  const { logout } = useAuth();
  
  // Extract all state and lifecycle from the custom hook
  const {
    jobs,
    pagination,
    setPagination,
    filters,
    setFilters,
    searchProfiles,
    fetchJobs,
    toggleApplied,
    clearFilters
  } = useJobs(logout);

  const totalJobs = pagination.total;
  const appliedCount = pagination.total_applied;
  const avgScore = Math.round(pagination.avg_score || 0);


  return (
    <div className="animate-slide-up">
      <div className="row g-3 g-md-4 mb-4 mb-md-5">
        <div className="col-12 col-md-4">
          <StatCard label="Jobs Found" value={totalJobs} color="primary" icon="bi-briefcase-fill" />
        </div>
        <div className="col-6 col-md-4">
          <StatCard label="Avg Match" value={`${avgScore}%`} color="warning" icon="bi-pie-chart-fill" />
        </div>
        <div className="col-6 col-md-4">
          <StatCard label="Applied" value={appliedCount} color="success" icon="bi-send-check-fill" />
        </div>
      </div>

      <div className="glass-panel overflow-hidden d-flex flex-column">
        <div className="p-3 border-bottom border-white-10 bg-black-20 transition-all">
            <FilterBar
            filters={filters}
            onChange={setFilters}
            searchProfiles={searchProfiles}
            onRefresh={() => fetchJobs(false)}
            onClear={clearFilters}
            />
        </div>
        <JobTable
            jobs={jobs}
            isGlobalView={!filters.search_profile_id}
            onToggleApplied={toggleApplied}
            pagination={pagination}
            onPageChange={(p) => setPagination(prev => ({ ...prev, page: p }))}
        />
      </div>
    </div>
  );
}
