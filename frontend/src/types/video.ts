export interface Video {
    id: number;
    project_id: number;
    source_type?: string;
    source_url?: string | null;
    status: string;
    processing_stage?: string;
    last_completed_clip?: number;
    file_path: string;
    duration?: number | null;
    publication_plan_enabled?: boolean;
    publication_max_per_day?: number | null;
    publication_start_date?: string | null;
    publication_times?: string | null;
    publication_timezone?: string | null;
    publication_plan_applied_at?: string | null;
    created_at: string;
    error_message?: string | null;
}
