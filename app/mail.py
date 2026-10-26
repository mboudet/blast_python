"""Email helpers.

Used both by the web application (to preview/send directly) and as a small CLI
script invoked from the submitted job script after a job completes.
"""
import argparse
import smtplib
from email.mime.text import MIMEText
from pathlib import Path


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


def send_email(
    subject: str,
    body: str,
    to_email: str,
    settings,
) -> None:
    """Send an email using SMTP if configured, otherwise fall back to the mail binary."""
    if settings.smtp_host:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["To"] = to_email
        msg["From"] = f"{settings.admin_name} <{settings.admin_email}>"
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(msg)
        return

    # Fallback to the system mail command.
    import subprocess

    cmd = ["mail", "-s", subject, "-r", settings.admin_email, to_email]
    subprocess.run(cmd, input=body, text=True, check=False)


def main() -> None:
    from .config import get_settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body-file", required=True)
    args = parser.parse_args()

    body = Path(args.body_file).read_text()
    send_email(args.subject, body, args.to, get_settings())


if __name__ == "__main__":
    main()
