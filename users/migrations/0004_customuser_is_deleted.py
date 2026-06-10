# Generated manually on 2026-06-10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_customuser_email_otp_attempts"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
    ]
