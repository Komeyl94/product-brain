/**
 * Symfony rules.
 *
 * Thinner than the Laravel set on purpose — there is no pilot Symfony repository to
 * calibrate against yet, so this covers only patterns that are wrong in any Symfony
 * version rather than anything that depends on a project's conventions. Extend it
 * once a real repository is onboarded.
 */

import { hasInterpolatedSql } from './shared.mjs';

const PHP = /\.php$/;
const CONTROLLER = /[/\\](Controller|Controllers)[/\\].*\.php$/;

export const symfonyRules = [
  {
    id: 'symfony/no-container-service-locator',
    stack: 'symfony',
    files: PHP,
    skip: (ctx) => ctx.isTest,
    test: /\$(this->)?container->get\s*\(|ContainerInterface.*->get\s*\(/,
    message:
      'Pulling services out of the container hides the dependency from the constructor and from the compiler. Inject the service instead.',
    doc: 'symfony/dependency-injection',
  },
  {
    id: 'symfony/no-annotation-routes',
    stack: 'symfony',
    files: PHP,
    raw: true,
    test: /^\s*\*\s*@Route\s*\(/,
    message:
      'Annotation routes were removed in Symfony 7. Use the PHP attribute: `#[Route(...)]`.',
    doc: 'symfony/routing',
  },
  {
    id: 'symfony/no-dql-interpolation',
    stack: 'symfony',
    files: PHP,
    custom: (lines, i) =>
      hasInterpolatedSql(lines[i], /->(createQuery|createNativeQuery|executeQuery|executeStatement)\s*\(/),
    message:
      'A variable is being interpolated into DQL/SQL — this is injection. Use `setParameter()` or a parameter array.',
    doc: 'symfony/security',
  },
  {
    id: 'symfony/no-entity-manager-in-controller',
    stack: 'symfony',
    files: CONTROLLER,
    test: /->(persist|flush|remove)\s*\(/,
    message:
      'Persistence in a controller couples HTTP to the database and cannot be reused or tested on its own. Move it into a service or handler.',
    doc: 'symfony/architecture',
  },
];
