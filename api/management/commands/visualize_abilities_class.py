# management/commands/visualize_abilities_class.py
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns
from django.core.management.base import BaseCommand
from io import BytesIO
import base64

from api.models import UserAbility, AssessmentResult, Assessment, User


class Command(BaseCommand):
    help = 'Generate visualizations comparing student abilities with specific assessment results'

    def add_arguments(self, parser):
        parser.add_argument('--assessment-id', type=int, required=True,
                            help='Assessment ID to analyze')
        parser.add_argument('--output', type=str, default='console',
                            choices=['console', 'html', 'png'],
                            help='Output format: console, html, or png')

    def handle(self, *args, **options):
        assessment_id = options['assessment_id']
        output_format = options['output']

        self.visualize_assessment_result(assessment_id, output_format)

    def visualize_assessment_result(self, assessment_id, output_format):
        try:
            # Get the specific assessment result
            assessment = Assessment.objects.get(pk=assessment_id)
            print("Assessment: ", assessment.name)

            class_group = assessment.class_owner

            print("Class Group", class_group)

            students = User.objects.filter(enrolled_class=class_group)
            results = AssessmentResult.objects.filter(
                assessment=assessment,
                user__in=students
            ).select_related('user')

            if not results:
                self.stdout.write(self.style.WARNING('No students have taken this assessment yet'))
                return

            # Prepare data for all students
            all_data = []

            for student_result in results:
                user = student_result.user
                abilities = UserAbility.objects.filter(user=user).select_related('category')

                print("Preparing Data for ", user.full_name)

                if not abilities.exists():
                    continue

                # Prepare data for categories in this assessment
                categories = assessment.selected_categories.all()

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
                    correct_answers = student_result.answers.filter(
                        question__in=questions,
                        is_correct=True
                    ).count()

                    normalized_score = correct_answers / total_questions

                    print('Name: ', user.full_name)
                    print('Category: ', category)
                    print('Score: ', normalized_score)

                    all_data.append({
                        'student_id': user.id,
                        'category': category.name,
                        'elo': ability.elo_ability,
                        'elo_time': ability.elo_time_ability,
                        'irt': ability.irt_ability,
                        'score': normalized_score,
                        'correct': correct_answers,
                        'total': total_questions
                    })

            if not all_data:
                self.stdout.write(self.style.WARNING('No matching category data found for any student'))
                return

            df = pd.DataFrame(all_data)

            if 'category' not in df.columns or df.empty:
                self.stdout.write(self.style.WARNING('No category data available for visualization'))
                return

            fig, axes = plt.subplots(2, 2, figsize=(18, 18))
            axes = axes.flatten()

            if not df.empty:
                df.boxplot(column='score', by='category', ax=axes[0])
                axes[0].set_title('Score Distribution by Category')
                axes[0].set_ylabel('Normalized Score (0-1)')
                axes[0].set_ylim(-0.1, 1.1)
                axes[0].tick_params(axis='x', rotation=45)

            print('Creating IRT')
            if 'irt' in df.columns:
                for category in df['category'].unique():
                    cat_data = df[df['category'] == category]
                    axes[1].scatter(
                        cat_data['irt'],
                        cat_data['score'],
                        label=category,
                        s=100,
                        alpha=0.7
                    )
                    correlation = cat_data['irt'].corr(cat_data['score'])
                    axes[1].text(
                        0.05, 0.95 - (0.05 * list(df['category'].unique()).index(category)),
                        f'{category} r = {correlation:.2f}',
                        transform=axes[1].transAxes,
                        fontsize=10,
                        bbox=dict(facecolor='white', alpha=0.7)
                    )

                axes[1].set_title('IRT Ability vs Performance')
                axes[1].set_xlabel('IRT Ability')
                axes[1].set_ylabel('Normalized Score (0-1)')
                axes[1].legend(loc='lower right', bbox_to_anchor=(0.95, 0.05),
                               framealpha=1, facecolor='white')
                axes[1].grid(True)

            print('Creating Elo')
            if 'elo' in df.columns:
                for category in df['category'].unique():
                    cat_data = df[df['category'] == category]
                    axes[2].scatter(
                        cat_data['elo'],
                        cat_data['score'],
                        label=category,
                        s=100,
                        alpha=0.7
                    )
                    correlation = cat_data['elo'].corr(cat_data['score'])
                    axes[2].text(
                        0.05, 0.95 - (0.05 * list(df['category'].unique()).index(category)),
                        f'{category} r = {correlation:.2f}',
                        transform=axes[2].transAxes,
                        fontsize=10,
                        bbox=dict(facecolor='white', alpha=0.7)
                    )

                axes[2].set_title('ELO Ability vs Performance')
                axes[2].set_xlabel('ELO Ability')
                axes[2].set_ylabel('Normalized Score (0-1)')
                axes[2].legend(loc='lower right', bbox_to_anchor=(0.95, 0.05),
                               framealpha=1, facecolor='white')
                axes[2].grid(True)

            print('Creating Elo Time')
            if 'elo_time' in df.columns:
                for category in df['category'].unique():
                    cat_data = df[df['category'] == category]
                    axes[3].scatter(
                        cat_data['elo_time'],
                        cat_data['score'],
                        label=category,
                        s=100,
                        alpha=0.7
                    )
                    correlation = cat_data['elo_time'].corr(cat_data['score'])
                    axes[3].text(
                        0.05, 0.95 - (0.05 * list(df['category'].unique()).index(category)),
                        f'{category} r = {correlation:.2f}',
                        transform=axes[3].transAxes,
                        fontsize=10,
                        bbox=dict(facecolor='white', alpha=0.7)
                    )

                axes[3].set_title('ELO-Time Ability vs Performance')
                axes[3].set_xlabel('ELO-Time Ability')
                axes[3].set_ylabel('Normalized Score (0-1)')
                axes[3].legend(loc='lower right', bbox_to_anchor=(0.95, 0.05),
                               framealpha=1, facecolor='white')
                axes[3].grid(True)

            plt.suptitle(f'Class Performance Analysis for Assessment {assessment.id}\n{assessment.name}', y=1.02)
            plt.tight_layout()

            if output_format == 'console':
                self.display_console(assessment, df)
            elif output_format == 'html':
                return self.fig_to_html(fig)
            else:
                filename = f'assessment_{assessment_id}_class_analysis.png'
                plt.savefig(filename, bbox_inches='tight')
                self.stdout.write(self.style.SUCCESS(f'Image saved as {filename}'))

        except AssessmentResult.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Assessment with ID {assessment_id} does not exist'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
        finally:
            plt.close()

    def display_console(self, result, df):
        assessment = result.assessment

        self.stdout.write(self.style.SUCCESS(
            f'\nClass Performance Analysis for Assessment {assessment.id}'
        ))
        self.stdout.write('=' * 80)
        self.stdout.write(f'Assessment Title: {assessment.title}')
        self.stdout.write(f'Class: {assessment.class_owner.name}')
        self.stdout.write(f'Total Students: {df["student_id"].nunique()}')
        self.stdout.write('=' * 80)

        self.stdout.write('\nPerformance Summary by Category:')
        self.stdout.write('-' * 80)

        # Calculate summary statistics
        summary = df.groupby('category').agg({
            'score': ['mean', 'median', 'std', 'count'],
            'elo': ['mean', 'median'],
            'elo_time': ['mean', 'median'],
            'irt': ['mean', 'median']
        })

        # Flatten multi-index columns
        summary.columns = ['_'.join(col).strip() for col in summary.columns.values]

        for category, row in summary.iterrows():
            self.stdout.write(
                f"{category.ljust(20)} | "
                f"Score: {row['score_mean']:.2%} (avg) | "
                f"ELO: {row['elo_mean']:.1f} | "
                f"ELO-Time: {row['elo_time_mean']:.1f} | "
                f"IRT: {row['irt_mean']:.2f} | "
                f"Students: {int(row['score_count'])}"
            )

    def fig_to_html(self, fig):
        """Convert matplotlib figure to HTML img tag"""
        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        return f'<img src="data:image/png;base64,{img_str}">'
