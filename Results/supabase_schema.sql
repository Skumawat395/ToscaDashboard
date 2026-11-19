create table if not exists public.execution_runs (
    id uuid primary key,
    started_at timestamptz not null,
    completed_at timestamptz not null
);

create table if not exists public.test_case_results (
    run_id uuid not null references public.execution_runs(id) on delete cascade,
    case_index integer not null,
    environment_name text not null,
    module_name text not null,
    testcase_name text not null,
    result text not null,
    start_time timestamptz,
    end_time timestamptz,
    created_by text,
    created_at timestamptz,
    primary key (run_id, case_index)
);

create index if not exists test_case_results_start_time_idx
    on public.test_case_results (start_time);

alter table public.execution_runs enable row level security;
alter table public.test_case_results enable row level security;

create or replace view public.execution_run_summary as
select
    r.id as run_id,
    r.started_at,
    r.completed_at,
    count(t.case_index) as total_tc,
    count(t.case_index) filter (
        where lower(trim(t.result)) in ('passed', 'pass')
    ) as passed_tc,
    count(t.case_index) filter (
        where lower(trim(t.result)) in ('failed', 'fail')
    ) as failed_tc,
    count(t.case_index) filter (
        where t.case_index is not null
          and lower(trim(t.result)) not in ('passed', 'pass', 'failed', 'fail')
    ) as other_tc
from public.execution_runs r
left join public.test_case_results t on t.run_id = r.id
group by r.id, r.started_at, r.completed_at;