# management/commands/visualize_assessment_result.py
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from django.core.management.base import BaseCommand
from io import BytesIO
import base64

from api.models import UserAbility, AssessmentResult, Assessment, User


class Command(BaseCommand):
    help = 'Generate visualizations comparing student abilities with specific assessment results'

    def add_arguments(self, parser):
        parser.add_argument('--student-id', type=int, required=True)
        parser.add_argument('--output', type=str, default='console',
                            choices=['console', 'html', 'png'],
                            help='Output format: console, html, or png')

    def handle(self, *args, **options):
        student_id = options['student_id']
        output_format = options['output']

        self.visualize_assessment_result(student_id, output_format)

    def visualize_assessment_result(self, student_id, output_format):
        try:
            user = User.objects.get(pk=student_id)
            assessment = Assessment.objects.get(class_owner=user.enrolled_class)
            result = AssessmentResult.objects.get(assessment=assessment, user=user)

            # Get all abilities for this user
            abilities = UserAbility.objects.filter(user=user).select_related('category')

            if not abilities.exists():
                self.stdout.write(self.style.WARNING(f'No ability data found for user {user.id}'))
                return

            # Prepare data for categories in this assessment
            categories = assessment.selected_categories.all()
            category_data = []

            for category in categories:
                ability = abilities.filter(category=category).first()
                if not ability:
                    continue

                # Get questions in this category for this assessment
                questions = assessment.questions.filter(category=category)
                total_questions = questions.count()
                if total_questions == 0:
                    continue

                # Calculate correct answers in this category
                correct_answers = result.answers.filter(
                    question__in=questions,
                    is_correct=True
                ).count()

                normalized_score = correct_answers / total_questions

                category_data.append({
                    'category': category.name,
                    'elo': ability.elo_ability,
                    'irt': ability.irt_ability,
                    'score': normalized_score,
                    'correct': correct_answers,
                    'total': total_questions
                })

            if not category_data:
                self.stdout.write(self.style.WARNING('No matching category data found'))
                return

            df = pd.DataFrame(category_data)

            # Create visualization
            fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(24, 6))
            fig.suptitle( f'Ability vs Performance for User ID: {user.id})\nScore: {result.score}')

            # Score Breakdown
            ax1.bar(df['category'], df['correct'], color='purple', label='Correct Answers')
            ax1.bar(df['category'], df['total'] - df['correct'], bottom=df['correct'],
                    color='gray', label='Incorrect Answers')
            ax1.set_title('Score Breakdown by Category')
            ax1.set_ylabel('Number of Questions')
            ax1.set_xticklabels(df['category'], rotation=45)
            ax1.legend()

            # IRT vs Performance
            ax2.scatter(df['irt'], df['score'], color='red', s=100)
            ax2.set_title('IRT Ability vs Actual Performance')
            ax2.set_xlabel('IRT Ability')
            ax2.set_ylabel('Normalized Score (0-1)')
            ax2.set_xlim(-4, 4)
            ax2.set_xticks(np.arange(-3, 3, 1))
            ax2.set_ylim(-0.1, 1.1)
            ax2.set_yticks(np.arange(0, 1.1, 0.1))

            if len(df) > 1:
                z = np.polyfit(df['irt'], df['score'], 1)
                p = np.poly1d(z)
                ax2.plot(df['irt'], p(df['irt']), "b--")
                ax2.text(0.05, 0.95, f'Correlation: {np.corrcoef(df["irt"], df["score"])[0, 1]:.2f}',
                         transform=ax2.transAxes, ha='left', va='top',
                         bbox=dict(facecolor='white', alpha=0.8))

            # ELO vs Performance (Scatter Plot)
            ax3.scatter(df['elo'], df['score'], color='green', s=100)
            ax3.set_title('ELO Ability vs Actual Performance')
            ax3.set_xlabel('ELO Ability')
            ax3.set_ylabel('Normalized Score (0-1)')
            ax3.set_ylim(-0.1, 1.1)
            ax3.set_yticks(np.arange(0, 1.1, 0.1))

            if len(df) > 1:
                z_elo = np.polyfit(df['elo'], df['score'], 1)
                p_elo = np.poly1d(z_elo)
                ax3.plot(df['elo'], p_elo(df['elo']), "b--")
                ax3.text(0.05, 0.95, f'Correlation: {np.corrcoef(df["elo"], df["score"])[0, 1]:.2f}',
                         transform=ax3.transAxes, ha='left', va='top',
                         bbox=dict(facecolor='white', alpha=0.8))

            plt.tight_layout()

            if output_format == 'console':
                self.display_console(result, df)
            elif output_format == 'html':
                return self.fig_to_html(fig)
            else:
                filename = f'assessment_result_for_{student_id}_analysis.png'
                plt.savefig(filename, bbox_inches='tight')
                self.stdout.write(self.style.SUCCESS(f'Image saved as {filename}'))

        except AssessmentResult.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User has not taken the initial assessment'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
        finally:
            plt.close()

    def display_console(self, result, df):
        user = result.user
        assessment = result.assessment

        self.stdout.write(self.style.SUCCESS(
            f'\nAbility vs Performance Analysis for AssessmentResult {result.id}'
        ))
        self.stdout.write('=' * 80)
        self.stdout.write(f'Student ID: {user.id})')
        self.stdout.write(f'Date: {result.start_time.date()}')
        self.stdout.write(f'Overall Score: {result.score}/{assessment.questions.count()}')
        self.stdout.write('=' * 80)

        self.stdout.write('\nCategory Breakdown:')
        self.stdout.write('-' * 80)
        self.stdout.write(
            f"{'Category'.ljust(20)} | "
            f"{'ELO'.rjust(8)} | "
            f"{'IRT'.rjust(8)} | "
            f"{'Score'.rjust(10)} | "
            f"{'Correct'.rjust(8)} | "
            f"{'Total'.rjust(6)}"
        )

        for _, row in df.iterrows():
            self.stdout.write(
                f"{row['category'].ljust(20)} | "
                f"{int(row['elo']):8} | "
                f"{row['irt']:8.2f} | "
                f"{row['score']:7.2%} | "
                f"{int(row['correct']):8} | "
                f"{int(row['total']):6}"
            )

        if len(df) > 1:
            corr = np.corrcoef(df['irt'], df['score'])[0, 1]
            self.stdout.write('\nIRT-Score Correlation:')
            self.stdout.write('-' * 80)
            self.stdout.write(f"Correlation coefficient: {corr:.2f}")
            if abs(corr) > 0.7:
                interpretation = "Strong correlation"
            elif abs(corr) > 0.3:
                interpretation = "Moderate correlation"
            else:
                interpretation = "Weak correlation"
            self.stdout.write(f"Interpretation: {interpretation}")

    def fig_to_html(self, fig):
        """Convert matplotlib figure to HTML img tag"""
        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        return f'<img src="data:image/png;base64,{img_str}">'