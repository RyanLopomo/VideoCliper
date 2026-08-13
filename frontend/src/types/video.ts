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
    created_at: string;
    error_message?: string | null;
}
