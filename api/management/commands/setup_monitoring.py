from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

class Command(BaseCommand):
    help = 'Set up periodic tasks for API monitoring every 30 seconds'

    def add_arguments(self, parser):
        parser.add_argument(
            '--target-profit',
            type=float,
            default=1000.0,
            help='Target profit amount (default: 1000.0)'
        )
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Disable periodic tasks'
        )

    def handle(self, *args, **options):
        target_profit = options['target_profit']
        disable = options['disable']
        
        if disable:
            # Disable all periodic tasks
            PeriodicTask.objects.filter(
                name__in=[
                    'Periodic API Check Every 30 Seconds',
                    'Connection Test Every 5 Minutes'
                ]
            ).update(enabled=False)
            
            self.stdout.write(
                self.style.WARNING('Disabled all periodic API monitoring tasks')
            )
            return
        
        # Create 30-second interval schedule
        schedule_30s, created = IntervalSchedule.objects.get_or_create(
            every=30,
            period=IntervalSchedule.SECONDS,
        )
        
        # Create 5-minute interval schedule for connection tests
        schedule_5m, created = IntervalSchedule.objects.get_or_create(
            every=5,
            period=IntervalSchedule.MINUTES,
        )
        
        # Create daily schedule for monthly cycle check
        schedule_daily, created = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.DAYS,
        )
        
        # Create or update the monthly cycle start task (daily check)
        monthly_task, created = PeriodicTask.objects.get_or_create(
            name='Monthly Strategy Start Check Daily',
            defaults={
                'interval': schedule_daily,
                'task': 'tasks.monthly_strategy_start_task',
                'enabled': True,
            }
        )
        
        if not created:
            monthly_task.enabled = True
            monthly_task.save()
        
        # Create or update the periodic adjustment check task (every 30 seconds)
        adjustment_task, created = PeriodicTask.objects.get_or_create(
            name='Periodic Adjustment Check Every 30 Seconds',
            defaults={
                'interval': schedule_30s,
                'task': 'tasks.periodic_adjustment_check',
                'args': json.dumps([target_profit]),
                'enabled': True,
            }
        )
        
        if not created:
            adjustment_task.interval = schedule_30s
            adjustment_task.args = json.dumps([target_profit])
            adjustment_task.enabled = True
            adjustment_task.save()
        
        # Create connection test task
        test_task, created = PeriodicTask.objects.get_or_create(
            name='Connection Test Every 5 Minutes',
            defaults={
                'interval': schedule_5m,
                'task': 'tasks.test_connection_task',
                'enabled': True,
            }
        )
        
        if not created:
            test_task.enabled = True
            test_task.save()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Successfully set up periodic tasks:\n'
                f'� Monthly cycle check: Daily (starts new cycles on 1st of month)\n'
                f'�📊 Position adjustment check: Every 30 seconds (target: ${target_profit})\n'
                f'🔗 Connection test: Every 5 minutes\n\n'
                f'🎯 Strategy Logic:\n'
                f'  1. First day of month: Sell call + put options in delta ranges\n'
                f'  2. Every 30 seconds: Check profit target and adjustments\n'
                f'  3. Close all positions when: realized_pnl + unrealized_pnl >= ${target_profit}\n'
                f'  4. Auto-close at expiry: 1:00 PM UTC on expiry date\n\n'
                f'To disable tasks, run: python manage.py setup_monitoring --disable'
            )
        )