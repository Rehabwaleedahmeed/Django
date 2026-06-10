# Generated manually on 2026-06-10

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="guest_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="order",
            name="guest_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="order",
            name="guest_phone",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
