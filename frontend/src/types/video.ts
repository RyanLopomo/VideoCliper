export interface Video {
    id: number;
    project_id: number;
    source_type?: string;
    source_url?: string | null;
    status: string;
    processing_stage?: string;
    last_completed_clip?: number;
    last_completed_step?: string | null;
    current_job_id?: string | null;
    processing_progress?: number | null;
    processing_message?: string | null;
    last_progress_at?: string | null;
    last_heartbeat?: string | null;
    error_type?: string | null;
    file_path: string;
    duration?: number | null;
    target_clip_count?: number | null;
    target_clip_duration?: number;
    publication_plan_enabled?: boolean;
    publication_max_per_day?: number | null;
    publication_start_date?: string | null;
    publication_times?: string | null;
    publication_timezone?: string | null;
    publication_plan_applied_at?: string | null;
    editing_style?: string;
    created_at: string;
    error_message?: string | null;
}
