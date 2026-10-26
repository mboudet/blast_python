"""Email helpers.

Provides the mail body builder used by the web application. Sending the actual
email happens on the compute node through the ``/bin/mail`` binary, so no SMTP
or CLI code is needed here.
"""


def build_mail_body(job, result_url_prefix: str, results_url: str, back_url: str) -> str:
    title = job.title or ""
    if title:
        title = f'"{title}" ({job.job_uid})'
    else:
        title = job.job_uid

    lines = []
    if job.title:
        lines.append(f'Your {job.program_name} job "{job.title}" ({job.job_uid}) is completed.')
    else:
        lines.append(f"Your {job.program_name} job {job.job_uid} is completed.")
    lines.append("")
    lines.append(f"Results are available at the following address: {results_url}")
    lines.append("")
    lines.append("You can also access directly to your results with the following links:")
    lines.append("")

    for file in job.result_viewers:
        lines.append(f"    {file.display_name}: {file.url}")

    if job.result_viewers:
        lines.append("")

    for file in job.result_files:
        lines.append(f"    {file.display_name}: {result_url_prefix}{file.fs_name}")

    lines.append("")
    lines.append(f"To launch another job, go to {back_url}")
    return "\n".join(lines)
