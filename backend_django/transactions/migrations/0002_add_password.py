from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchantfeeprofile',
            name='password',
            field=models.CharField(default='pinelabs123', max_length=128),
        ),
    ]
