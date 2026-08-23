(function () {
    'use strict';

    const HTTP_METHODS = new Set(['get', 'post', 'put', 'patch', 'delete', 'options', 'head']);
    const groupsRoot = document.getElementById('apiGroups');
    const status = document.getElementById('apiStatus');
    const filter = document.getElementById('endpointFilter');

    function createElement(tagName, className, text) {
        const element = document.createElement(tagName);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    function schemaLabel(schema) {
        if (!schema) return 'value';
        if (schema.$ref) return schema.$ref.split('/').pop();
        if (schema.type === 'array') return `array<${schemaLabel(schema.items)}>`;
        return schema.type || 'value';
    }

    function appendList(section, heading, entries) {
        if (!entries.length) return;
        section.appendChild(createElement('h3', '', heading));
        const list = createElement('ul', 'api-list');
        entries.forEach((entry) => {
            const item = createElement('li');
            item.appendChild(createElement('code', '', entry.label));
            item.appendChild(document.createTextNode(` — ${entry.description}`));
            list.appendChild(item);
        });
        section.appendChild(list);
    }

    function createEndpoint(path, method, operation, inheritedParameters) {
        const endpoint = createElement('details', 'api-endpoint');
        const summary = createElement('summary');
        const methodLabel = createElement('span', 'api-method', method.toUpperCase());
        methodLabel.dataset.method = method;
        summary.appendChild(methodLabel);
        summary.appendChild(createElement('code', 'api-path', path));
        summary.appendChild(createElement('span', 'api-summary', operation.summary || operation.operationId || ''));
        endpoint.appendChild(summary);

        const detail = createElement('div', 'api-detail');
        if (operation.description) detail.appendChild(createElement('p', '', operation.description));

        const parameters = [...(inheritedParameters || []), ...(operation.parameters || [])].map((parameter) => ({
            label: `${parameter.name} (${parameter.in}${parameter.required ? ', required' : ''})`,
            description: `${schemaLabel(parameter.schema)}${parameter.description ? ` — ${parameter.description}` : ''}`,
        }));
        appendList(detail, 'Parameters', parameters);

        if (operation.requestBody) {
            const content = operation.requestBody.content || {};
            const bodyTypes = Object.entries(content).map(([mediaType, value]) => ({
                label: mediaType,
                description: schemaLabel(value.schema),
            }));
            appendList(detail, 'Request body', bodyTypes);
        }

        const responses = Object.entries(operation.responses || {}).map(([code, response]) => ({
            label: code,
            description: response.description || 'Response',
        }));
        appendList(detail, 'Responses', responses);
        endpoint.appendChild(detail);

        endpoint.dataset.search = [
            method,
            path,
            operation.summary,
            operation.description,
            operation.operationId,
            ...(operation.tags || []),
        ].filter(Boolean).join(' ').toLocaleLowerCase();
        return endpoint;
    }

    function applyFilter() {
        const query = filter.value.trim().toLocaleLowerCase();
        let visible = 0;
        document.querySelectorAll('.api-endpoint').forEach((endpoint) => {
            endpoint.hidden = Boolean(query) && !endpoint.dataset.search.includes(query);
            if (!endpoint.hidden) visible += 1;
        });
        document.querySelectorAll('.api-group').forEach((group) => {
            group.hidden = !group.querySelector('.api-endpoint:not([hidden])');
        });
        status.textContent = `${visible} endpoint${visible === 1 ? '' : 's'}`;
    }

    function groupFor(path, operation) {
        if (operation.tags?.length) return operation.tags[0];
        if (path.startsWith('/api/stats')) return 'Statistics';
        if (path.startsWith('/api/privacy')) return 'Privacy';
        if (path.startsWith('/api/auth')) return 'Authentication';
        if (path.startsWith('/api/servers') || path.startsWith('/api/source')) return 'Connections';
        if (path.startsWith('/health')) return 'Health';
        if (path === '/metrics') return 'Monitoring';
        return 'Application';
    }

    function renderSchema(schema) {
        const grouped = new Map();
        Object.entries(schema.paths || {}).forEach(([path, pathItem]) => {
            Object.entries(pathItem).forEach(([method, operation]) => {
                if (!HTTP_METHODS.has(method) || !operation) return;
                const groupName = groupFor(path, operation);
                if (!grouped.has(groupName)) grouped.set(groupName, []);
                grouped.get(groupName).push(createEndpoint(path, method, operation, pathItem.parameters));
            });
        });

        groupsRoot.replaceChildren();
        [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right)).forEach(([name, endpoints]) => {
            const group = createElement('section', 'api-group');
            group.appendChild(createElement('h2', '', name));
            const list = createElement('div', 'api-endpoints');
            endpoints.forEach((endpoint) => list.appendChild(endpoint));
            group.appendChild(list);
            groupsRoot.appendChild(group);
        });

        const info = schema.info || {};
        document.title = `${info.title || 'Navidrome Statistic'} API`;
        document.getElementById('apiDescription').textContent = info.description
            || `OpenAPI ${schema.openapi || ''} · Version ${info.version || 'unknown'}`;
        applyFilter();
    }

    async function loadSchema() {
        try {
            const response = await fetch('/openapi.json', { credentials: 'same-origin' });
            if (!response.ok) throw new Error(`OpenAPI request returned ${response.status}`);
            renderSchema(await response.json());
        } catch (error) {
            groupsRoot.replaceChildren(createElement('p', 'api-error', 'The API schema could not be loaded. Sign in again or check the service logs.'));
            status.textContent = 'Unavailable';
            console.error('Unable to load OpenAPI schema', error);
        }
    }

    filter.addEventListener('input', applyFilter);
    loadSchema();
}());
